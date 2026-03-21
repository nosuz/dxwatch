(function () {
  const COLOR_MAP = {
    160: '#332288',  // indigo     L=0.036  darkest
    80:  '#882255',  // wine       L=0.071
    40:  '#117733',  // dark green L=0.137
    30:  '#CC3311',  // red        L=0.152
    20:  '#0077BB',  // blue       L=0.171
    17:  '#EE3377',  // magenta    L=0.219
    15:  '#CC6677',  // rose       L=0.236
    12:  '#009E73',  // teal       L=0.262
    10:  '#0099CC',  // cyan-blue  L=0.272
    6:   '#AA9900',  // olive      L=0.314
    2:   '#E69F00',  // amber      L=0.419  lightest
    0:   '#888888',  // other / unknown
  };

  const BAND_CUES = {
    160: '-', 80: '|', 40: '/', 30: '\\', 20: 'x', 17: '',
    15: 'x', 12: '\\', 10: '/', 6: '|', 2: '-', 0: '',
  };

  const BAND_CUE_COLORS = {
    160: '#fff', 80: '#fff', 40: '#fff', 30: '#fff', 20: '#fff', 17: '#fff',
    15: '#000', 12: '#000', 10: '#000', 6: '#000', 2: '#000', 0: '#fff',
  };

  var DOT_BANDS = new Set([17]);

  function haloLine(x1, y1, x2, y2, c) {
    var h = c === '#fff' ? '#000' : '#fff';
    var attrs = '" stroke-linecap="round"/>';
    return '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '" stroke="' + h + '" stroke-width="4' + attrs +
           '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '" stroke="' + c + '" stroke-width="2' + attrs;
  }

  function cueLine(cueKey, c) {
    switch (cueKey) {
      case '-':  return haloLine(6,10,14,10,c);
      case '|':  return haloLine(10,6,10,14,c);
      case '/':  return haloLine(6,14,14,6,c);
      case '\\': return haloLine(6,6,14,14,c);
      case 'x':  return haloLine(6,14,14,6,c) + haloLine(6,6,14,14,c);
      default:   return '';
    }
  }

  function bandLegendSvg(band, color) {
    var cue = cueLine(BAND_CUES[band], BAND_CUE_COLORS[band] || '#fff');
    var dot = DOT_BANDS.has(band) ? '<circle cx="10" cy="10" r="3" fill="' + (band === 17 ? '#000' : '#fff') + '"/>' : '';
    return '<svg width="20" height="20" xmlns="http://www.w3.org/2000/svg">' +
           '<rect x="0" y="0" width="20" height="20" rx="2" fill="' + color + '"/>' +
           cue + dot + '</svg>';
  }

  function fillLegend(onChange) {
    const legendDiv = document.getElementById('legend');
    if (!legendDiv) return null;
    legendDiv.innerHTML = '';

    var legendBands = [
      [160, '160m'], [80, '80m'], [40, '40m'], [30, '30m'], [20, '20m'],
      [17, '17m'], [15, '15m'], [12, '12m'], [10, '10m'], [6, '6m'],
      [2, '2m'], [0, 'Other'],
    ];

    var allBands = legendBands.map(function (e) { return e[0]; });
    var saved = window.PskCookies.getCookie('pskr_bands');
    var selected = saved
      ? new Set(saved.split(',').map(Number))
      : new Set(allBands);

    legendBands.forEach(function (entry) {
      var band = entry[0];
      const item = document.createElement('div');
      item.className = 'legend-item';

      const colorBox = document.createElement('div');
      colorBox.className = 'legend-color';
      colorBox.innerHTML = bandLegendSvg(band, COLOR_MAP[band]);

      const label = document.createElement('span');
      label.textContent = entry[1];

      item.appendChild(colorBox);
      item.appendChild(label);
      legendDiv.appendChild(item);

      if (!selected.has(band)) item.classList.add('off');

      item.addEventListener('click', function () {
        if (selected.has(band)) {
          selected.delete(band);
          item.classList.add('off');
        } else {
          selected.add(band);
          item.classList.remove('off');
        }
        window.PskCookies.setCookie('pskr_bands', Array.from(selected).join(','), 365);
        if (onChange) onChange(new Set(selected));
      });
    });

    return new Set(selected);
  }

  window.PskUi = {
    COLOR_MAP,
    BAND_CUES,
    BAND_CUE_COLORS,
    bandLegendSvg,
    fillLegend,
  };
})();
