import * as d3selection from 'd3-selection';

var d3 = Object.assign({}, d3selection);

function writeSyntenicRegion(syntenies, regionID, ideo) {
  return syntenies.append('g')
    .attr('class', 'syntenicRegion')
    .attr('id', regionID)
    .on('click', function() {
      var activeRegion = this;
      var others = d3.selectAll(ideo.selector + ' .syntenicRegion')
        .filter(function() {
          return (this !== activeRegion);
        });

      others.classed('hidden', !others.classed('hidden'));
    })
    .on('mouseover', function() {
      var activeRegion = this;
      d3.selectAll(ideo.selector + ' .syntenicRegion')
        .filter(function() { return (this !== activeRegion); })
        .classed('ghost', true);
    })
    .on('mouseout', function() {
      d3.selectAll(ideo.selector + ' .syntenicRegion')
        .classed('ghost', false);
    });
}

function getRegionsR1AndR2(regions, xOffset, ideo) {
  var r1, r2;

  r1 = regions.r1;
  r2 = regions.r2;

  r1.startPx = ideo.convertBpToPx(r1.chr, r1.start) + xOffset;
  r1.stopPx = ideo.convertBpToPx(r1.chr, r1.stop) + xOffset;
  r2.startPx = ideo.convertBpToPx(r2.chr, r2.start) + xOffset;
  r2.stopPx = ideo.convertBpToPx(r2.chr, r2.stop) + xOffset;

  return [r1, r2];
}

function writeSyntenicRegionPolygons(syntenicRegion, x1, x2, r1, r2, regions) {
  var color, opacity;

  color = ('color' in regions) ? regions.color : '#CFC';
  opacity = ('opacity' in regions) ? regions.opacity : 1;

  syntenicRegion.append('polygon')
    .attr('points',
      x1 + ', ' + r1.startPx + ' ' +
      x1 + ', ' + r1.stopPx + ' ' +
      x2 + ', ' + r2.stopPx + ' ' +
      x2 + ', ' + r2.startPx
    )
    .attr('style', 'fill: ' + color + '; fill-opacity: ' + opacity);
}

function writeSyntenicRegionLines(syntenicRegion, x1, x2, r1, r2) {
  syntenicRegion.append('line')
    .attr('class', 'syntenyBorder')
    .attr('x1', x1)
    .attr('x2', x2)
    .attr('y1', r1.startPx)
    .attr('y2', r2.startPx);

  syntenicRegion.append('line')
    .attr('class', 'syntenyBorder')
    .attr('x1', x1)
    .attr('x2', x2)
    .attr('y1', r1.stopPx)
    .attr('y2', r2.stopPx);
}

function writeSyntenicRegions(syntenicRegions, syntenies, xOffset, ideo) {
  var i, regions, r1, r2, regionID, syntenicRegion, chrWidth, x1, x2;

  for (i = 0; i < syntenicRegions.length; i++) {
    regions = syntenicRegions[i];

    [r1, r2] = getRegionsR1AndR2(regions, xOffset, ideo)

    regionID = (
      r1.chr.id + '_' + r1.start + '_' + r1.stop + '_' +
      '__' +
      r2.chr.id + '_' + r2.start + '_' + r2.stop
    );

    syntenicRegion = writeSyntenicRegion(syntenies, regionID, ideo);

    chrWidth = ideo.config.chrWidth;
    x1 = ideo._layout.getChromosomeSetYTranslate(0);
    x2 = ideo._layout.getChromosomeSetYTranslate(1) - chrWidth;

    writeSyntenicRegionPolygons(syntenicRegion, x1, x2, r1, r2, regions);
    writeSyntenicRegionLines(syntenicRegion, x1, x2, r1, r2);
  }
}

function reportPerformance(t0, ideo) {
  var t1 = new Date().getTime();
  if (ideo.config.debug) {
    console.log('Time in drawSyntenicRegions: ' + (t1 - t0) + ' ms');
  }
}

/**
 * Draws a trapezoid connecting a genomic range on
 * one chromosome to a genomic range on another chromosome;
 * a syntenic region.
 */
function drawSynteny(syntenicRegions) {
  var syntenies, xOffset, 
    t0 = new Date().getTime(),
    ideo = this;

  syntenies = d3.select(ideo.selector)
    .insert('g', ':first-child')
    .attr('class', 'synteny');

  xOffset = ideo._layout.margin.left;

  writeSyntenicRegions(syntenicRegions, syntenies, xOffset, ideo);

  reportPerformance(t0, ideo);
}

export {drawSynteny}