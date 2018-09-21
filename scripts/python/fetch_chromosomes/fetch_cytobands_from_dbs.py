"""Fetch cytogenetic band data from third-party MySQL databases
"""

# TODO:
# - Bonus: Convert this data into AGP 2.0, send data missing from NCBI to them

import os
import json
from concurrent.futures import ThreadPoolExecutor
import argparse

from . import settings


parser = argparse.ArgumentParser(
    description=__doc__,
    formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('--output_dir',
    help='Directory to send output data to',
    default='../../data/bands/native/')
# parser.add_argument('--fresh_run',
#     help='Do you want to use cached data, or fresh data fetched over ' +
#          'the Internet?',
#     default='True')
# parser.add_argument('--fill_cache',
#     help='Do you want to populate the cache?  Only applicable for fresh runs.',
#     default='False')
args = parser.parse_args()


def t_or_f(arg):
    ua = str(arg).upper()
    if 'TRUE'.startswith(ua):
        return True
    elif 'FALSE'.startswith(ua):
        return False
    else:
        pass  #error condition maybe?


# eweitz, 2017-12-01:
# The arguments '--fresh_run=False and --fresh_run=False' do not yet work.
# The code related to these arguments is a work in progress.
# They are intended to speed up development by enabling runs to
# bypass remote querying and download.
fresh_run = True # t_or_f(args.fresh_run)
fill_cache = False #t_or_f(args.fill_cache)
output_dir = args.output_dir
cache_dir = output_dir + 'cache/'
log_name = 'fetch_cytobands_from_dbs'

from . import settings
logger = settings.init(fresh_run, fill_cache, output_dir, cache_dir, log_name)

from .utils import *
from .ucsc import *
from .ensembl import *
from .genomaize import *

if os.path.exists(output_dir) is False:
    os.mkdir(output_dir)

# Caching scenarios
#
# | fresh_run  | True | True  | False | False |
# | fill_cache | True | False | True  | False |
# | Scenario   | A    | B     | C     | D     |
#
# Scenario A: Repopulate cache.  Slow run, prepare later cache.
# Scenario B: For production.  Slow run, don't write to cache.
# Scenario C: No-op.  Illogical state, throw error.
# Scenario D: For development, or debugging.  Fast run, usable offline.
#
# Scenario D can be useful when working without Internet access, e.g. on a
# train or in rural areas.  It also enables much faster iteration even when
# connectivity is good.  Be sure to run Scenario A first, though!
if fresh_run is False and fill_cache:
    raise ValueError(
        'Error: Attempting to use cache, but no cache exists.  ' +
        'Use other arguments, e.g. "--fill_cache=True --fill_cache=True".'
    )

if os.path.exists(cache_dir) is False:
    if fill_cache:
        os.mkdir(cache_dir)
    if fresh_run is False:
        raise ValueError(
            'No cache available.  ' +
            'Run with "--fresh_run=True --fill_cache=True" then try again.'
        )

time_ncbi = 0
time_ucsc = 0
time_ensembl = 0

times = {'ncbi': 0, 'ucsc': 0, 'ensembl': 0}


def merge_centromeres(bands_by_chr, centromeres):
    """Adds p and q arms to cytobands; thus adds centromere to each chromosome.

    This is a special case for Zea mays (maize, i.e. corn).
    Ensembl Genomes provides band data with no cytogenetic arm assignment.
    Genomaize provides centromere positions for each chromosome.
    This function merges those two datasets to provide input directly
    useable to Ideogram.js.
    """
    logger.info('Entering merge_centromeres')
    new_bands = {}

    for chr in bands_by_chr:
        bands = bands_by_chr[chr]
        new_bands[chr] = []
        centromere = centromeres[chr]
        cen_start, cen_stop = centromere
        pcen_index = None

        j = 0
        for i, band in enumerate(bands):
            new_band = band
            band_start, band_stop = band[1:3]
            if int(band_stop) < int(cen_start):
                arm = 'p'
            else:
                arm = 'q'

                if int(band_start) < int(cen_stop):
                    # Omit any q-arm bands that start before q-arm pericentromeric band
                    if chr == '1':
                        logger.info('Omit band:')
                        logger.info(band)
                    j += 1
                    continue

                if pcen_index is None:
                    pcen_index = i - j

                    # Extend nearest p-arm band's stop coordinate to the
                    # p_cen's start coordinate (minus 1)
                    cen_start_pre = str(int(cen_start) - 1)
                    new_bands[chr][i - j - 1][3] = cen_start_pre
                    new_bands[chr][i - j - 1][5  ] = cen_start_pre

                    # Extend nearest q-arm band's start coordinate to the
                    # q_cen's stop coordinate (plus 1)
                    cen_stop_post = str(int(cen_stop) + 1)
                    bands[i + j][1] = cen_stop_post
                    bands[i + j][3] = cen_stop_post

                    # Coordinates of the centromere itself
                    cen_mid = int(cen_start) + round((int(cen_stop)-int(cen_start))/2)

                    pcen = [
                        'p', 'pcen', cen_start, str(cen_mid - 1),
                        cen_start, str(cen_mid - 1), 'acen'
                    ]
                    qcen = [
                        'q', 'qcen', str(cen_mid), cen_stop,
                        str(cen_mid), cen_stop, 'acen'
                    ]
            new_band.insert(0, arm)
            new_bands[chr].append(new_band)
        if pcen_index is not None:
            new_bands[chr].insert(pcen_index, qcen)
            new_bands[chr].insert(pcen_index, pcen)
    return new_bands


def parse_centromeres(bands_by_chr):
    """Adds p and q arms to cytobands, by parsing embedded centromere bands.

    This is a special case for assigning cytogenetic arms to certain organisms
    from Ensembl Genomes, including: Aspergillus fumigatus, Aspergillus
    nidulans, Aspergillus niger, Aspergillus oryzae (various fungi);
    Oryza sativa (rice); and Hordeum vulgare (barley).

    Bands are assigned an arm based on their position relative to the embedded
    centromere.
    """
    logger.info('Entering parse_centromeres')

    # If centromeres aren't embedded in the input banding data,
    # then simply return the input without modification.
    has_centromere = False
    for chr in bands_by_chr:
        bands = bands_by_chr[chr]
        for band in bands:
            stain = band[-1]
            if stain == 'acen':
                has_centromere = True
    if has_centromere is False:
        return bands_by_chr

    new_bands = {}

    for chr in bands_by_chr:
        bands = bands_by_chr[chr]
        new_bands[chr] = []

        # On each side of the centromere -- the p-arm side and the q-arm
        # side -- there is a band with a "stain" value of "acen".  Here,
        # we find the index of the acen band on the p-arm side.  That
        # band and all bands to the left of it are on the p arm.  All
        # bands to the right of it are on the q arm.
        pcen_index = None
        for i, band in enumerate(bands):
            stain = band[-1]
            if stain == 'acen':
                pcen_index = i
        for i, band in enumerate(bands):
            arm = ''
            if pcen_index is not None:
                if i < pcen_index:
                    arm = 'p'
                else:
                    arm = 'q'
            band.insert(0, arm)
            new_bands[chr].append(band)

    return new_bands


def patch_telomeres(bands_by_chr):
    """Account for special case with Drosophila melanogaster
    """
    for chr in bands_by_chr:
        first_band = bands_by_chr[chr][0]
        start = first_band[1]
        if start != '1':
            stop = str(int(start) - 1)
            pter_band = ['pter', '1', stop, '1', stop, 'gpos']
            bands_by_chr[chr].insert(0, pter_band)

    new_bands = {}
    for chr in bands_by_chr:
        new_bands[chr] = []
        for band in bands_by_chr[chr]:
            band.insert(0, 'q')
            new_bands[chr].append(band)
    bands_by_chr = new_bands

    return bands_by_chr


def pool_processing(party):
    """Called once per "party" (i.e. UCSC, Ensembl, or GenoMaize)
    to fetch cytoband data from each.
    """
    global times
    global unfound_dbs
    print('in fetch_cytobands_from_dbs, pool_processing')
    logger.info('Entering pool processing, party: ' + party)
    if party == 'ensembl':
        org_map = fetch_from_ensembl_genomes(times, logger)
    elif party == 'ucsc':
        org_map, times, unfound_dbs_subset =\
            fetch_from_ucsc(logger, times, unfound_dbs)
        unfound_dbs += unfound_dbs_subset
    elif party == 'genomaize':
        org_map = fetch_maize_centromeres(output_dir)

    logger.info('exiting pool processing')
    return [party, org_map, times]


party_list = []
unfound_dbs = []
zea_mays_centromeres = {}

def main():
    global unfound_dbs
    
    # Request data from all parties simultaneously
    num_threads = 3
    with ThreadPoolExecutor(max_workers=num_threads) as pool:
        print ('in fetch_cytobands_from_dbs, main')
        parties = ['ensembl', 'ucsc', 'genomaize']
        for result in pool.map(pool_processing, parties):
            party = result[0]
            if party == 'genomaize':
                zea_mays_centromeres = result[1]
            else:
                party_list.append(result)

    print ('in fetch_cytobands_from_dbs, main after TPE')
    logger.info('')
    logger.info('UCSC databases not mapped to GenBank assembly IDs:')
    logger.info(', '.join(unfound_dbs))
    logger.info('')

    # Third parties (e.g. UCSC, Ensembl) can have data for the same organism.
    # Convert any such duplicate data into a non-redundant (NR) organism map.
    nr_org_map = {}
    seen_orgs = {}
    for party, org_map, times in party_list:
        logger.info('Iterating organisms from ' + party)
        for org in org_map:
            logger.info('\t' + org)
            if org in seen_orgs:
                logger.info('Already saw ' + org)
                continue
            nr_org_map[org] = org_map[org]

    manifest = {}

    for org in nr_org_map:

        asm_data = sorted(nr_org_map[org], reverse=True)[0]
        genbank_accession, db, bands_by_chr = asm_data

        manifest[org] = [genbank_accession, db]

        if org == 'drosophila-melanogaster':
            bands_by_chr = patch_telomeres(bands_by_chr)

        # Assign cytogenetic arms for each band
        if org == 'zea-mays':
            bands_by_chr = merge_centromeres(bands_by_chr, zea_mays_centromeres)
        else:
            bands_by_chr = parse_centromeres(bands_by_chr)

        # Collapse chromosome-to-band dict, making it a list of strings
        band_list = []
        chrs = natural_sort(list(bands_by_chr.keys()))
        for chr in chrs:
            bands = bands_by_chr[chr]
            for band in bands:
                band_list.append(chr + ' ' + ' '.join(band))

        # Write actual cytoband data to file,
        # e.g. ../data/bands/native/anopheles-gambiae.js
        with open(output_dir + org + '.js', 'w') as f:
            f.write('window.chrBands = ' + str(band_list))

    logger.info('')

    # How long did each part take?
    logger.info('time_ucsc:')
    logger.info(time_ucsc)
    logger.info('time_ncbi:')
    logger.info(time_ncbi)
    logger.info('time_ensembl:')
    logger.info(time_ensembl)

    print('exiting main, fetch_cytobands_from_dbs')
    return manifest


if __name__ == '__main__':
    main()