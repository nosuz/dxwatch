(function () {
  const COLOR_MAP = {
    160: '#800000',
    80: '#FF4500',
    60: '#FF8C00',
    40: 'red',
    30: 'orange',
    20: 'yellow',
    17: '#ADFF2F',
    15: 'green',
    12: 'cyan',
    10: 'blue',
    6: '#4B0082'
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
