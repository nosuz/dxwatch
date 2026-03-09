(function () {
  function latlonToMaidenhead(lat, lon) {
    lat += 90;
    lon += 180;
    const A = 'A'.charCodeAt(0);
    const L1 = String.fromCharCode(A + Math.floor(lon / 20));
    const L2 = String.fromCharCode(A + Math.floor(lat / 10));
    const lonRem = lon % 20;
    const latRem = lat % 10;
    const N1 = Math.floor(lonRem / 2);
    const N2 = Math.floor(latRem / 1);
    const lonRem2 = lonRem % 2;
    const latRem2 = latRem % 1;
    const L3 = String.fromCharCode(A + Math.floor(lonRem2 * 12.0));
    const L4 = String.fromCharCode(A + Math.floor(latRem2 * 24.0));
    return L1 + L2 + N1 + N2 + L3 + L4;
  }

  function addGrid(map) {
    const gridLayers = L.layerGroup().addTo(map);

    function drawGrid() {
      gridLayers.clearLayers();

      const zoom = map.getZoom();
      let latStep;
      let lonStep;
      let labelDigits;

      if (zoom < 6) {
        latStep = 10;
        lonStep = 20;
        labelDigits = 2;
      } else {
        latStep = 1;
        lonStep = 2;
        labelDigits = 4;
      }

      const bounds = map.getBounds();
      const latStart = Math.floor(bounds.getSouth() / latStep) * latStep;
      const latEnd = Math.ceil(bounds.getNorth() / latStep) * latStep;
      let lonStart = Math.floor(bounds.getWest() / lonStep) * lonStep;
      let lonEnd = Math.ceil(bounds.getEast() / lonStep) * lonStep;

      lonStart = Math.max(lonStart, -180);
      lonEnd = Math.min(lonEnd, 180 - lonStep);

      for (let lat = latStart; lat <= latEnd; lat += latStep) {
        for (let lon = lonStart; lon <= lonEnd; lon += lonStep) {
          const centerLat = lat + latStep / 2;
          const centerLon = lon + lonStep / 2;

          L.rectangle([[lat, lon], [lat + latStep, lon + lonStep]], {
            color: '#888',
            weight: 1,
            fillOpacity: 0,
          }).addTo(gridLayers);

          const locator = latlonToMaidenhead(centerLat, centerLon).substring(0, labelDigits);
          L.marker([centerLat, centerLon], {
            icon: L.divIcon({
              className: 'grid-label',
              iconSize: null,
              iconAnchor: [10, 10],
              html: '<span style="font-size:20px; color: rgba(255,0,0,0.5); font-weight:bold;">' + locator + '</span>',
            }),
          }).addTo(gridLayers);
        }
      }
    }

    drawGrid();
    map.on('zoomend', drawGrid);
    map.on('moveend', drawGrid);

    return { drawGrid };
  }

  window.PskGrid = { addGrid };
})();
