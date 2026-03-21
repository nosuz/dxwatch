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

  const DOT_BANDS = new Set([40, 30, 20]);

  function bandBackground(band, color) {
    return DOT_BANDS.has(band)
      ? 'radial-gradient(circle, #fff 22%, ' + color + ' 23%)'
      : color;
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
      colorBox.style.background = bandBackground(band, COLOR_MAP[band]);

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
    DOT_BANDS,
    bandBackground,
    fillLegend,
  };
})();
