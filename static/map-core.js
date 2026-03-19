(function () {
  function addTerminator(map, enabled) {
    if (!enabled || !L.terminator) return null;
    const terminator = L.terminator({ fillOpacity: 0.15 }).addTo(map);
    setInterval(function () {
      terminator.setTime(new Date());
    }, 60 * 1000);
    return terminator;
  }

  function createMap(mapOptions) {
    const map = L.map('map', {
      minZoom: mapOptions.minZoom,
      maxZoom: mapOptions.maxZoom,

    }).setView(mapOptions.center, mapOptions.zoom);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

    if (mapOptions.maxBounds) {
      map.setMaxBounds(mapOptions.maxBounds);
    }

    addTerminator(map, mapOptions.showTerminator);

    if (mapOptions.showGrid) {
      window.PskGrid.addGrid(map);
    }

    return map;
  }

  window.PskMap = { createMap };
})();
