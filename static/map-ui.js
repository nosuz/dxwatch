(function () {
  const COLOR_MAP = {
    160: '#332288',
    80: '#E69F00',
    60: '#0077BB',
    40: '#009E73',
    30: '#AA9900',
    20: '#CC3311',
    17: '#D55E00',
    15: '#CC6677',
    12: '#555555',
    10: '#AA4499',
    6: '#44AA99'
  };

  function fillLegend() {
    const legendDiv = document.getElementById('legend');
    if (!legendDiv) return;
    legendDiv.innerHTML = '';

    Object.keys(COLOR_MAP).forEach(function (key) {
      const item = document.createElement('div');
      item.className = 'legend-item';

      const colorBox = document.createElement('div');
      colorBox.className = 'legend-color';
      colorBox.style.backgroundColor = COLOR_MAP[key];

      const label = document.createElement('span');
      label.textContent = key + 'm';

      item.appendChild(colorBox);
      item.appendChild(label);
      legendDiv.appendChild(item);
    });
  }

  window.PskUi = {
    COLOR_MAP,
    fillLegend,
  };
})();
