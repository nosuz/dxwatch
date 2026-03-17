(function () {
  var ALL_BANDS = [160, 80, 60, 40, 30, 20, 17, 15, 12, 10, 6];

  var dialog, titleBar, titleText, heatmapEl, bandsEl;
  var currentCallsign = '';
  var activityData = [];
  var selectedBands = null; // null = all bands

  // ── Color scale ──────────────────────────────────────────────────
  function cellColor(count, maxCount) {
    if (count === 0 || maxCount === 0) return '#262636';
    var t = Math.log(count + 1) / Math.log(maxCount + 1);
    var lightness = Math.round(15 + t * 60);
    return 'hsl(35,90%,' + lightness + '%)';
  }

  // ── Date helpers ─────────────────────────────────────────────────
  function getLast7Days() {
    var days = [];
    for (var i = 6; i >= 0; i--) {
      var d = new Date(Date.now() - i * 86400000);
      days.push(d.toISOString().slice(0, 10));
    }
    return days;
  }

  // ── Grid building ─────────────────────────────────────────────────
  function buildGrid(data, bands) {
    var days = getLast7Days();
    var grid = {};
    days.forEach(function (d) { grid[d] = new Array(24).fill(0); });
    data.forEach(function (row) {
      if (bands && bands.indexOf(row.band) === -1) return;
      var day = row.hour_utc.slice(0, 10);
      var hour = parseInt(row.hour_utc.slice(11, 13), 10);
      if (grid[day] !== undefined) grid[day][hour] += row.spot_count;
    });
    return { days: days, grid: grid };
  }

  // ── Heatmap render ────────────────────────────────────────────────
  function renderHeatmap() {
    var result = buildGrid(activityData, selectedBands);
    var days = result.days;
    var grid = result.grid;

    var maxCount = 0;
    days.forEach(function (d) {
      grid[d].forEach(function (c) { if (c > maxCount) maxCount = c; });
    });

    var html = '<table class="act-table"><thead><tr><th></th>';
    for (var h = 0; h < 24; h++) {
      html += '<th>' + (h < 10 ? '0' + h : '' + h) + '</th>';
    }
    html += '</tr></thead><tbody>';

    days.forEach(function (day) {
      html += '<tr><td class="act-day">' + day.slice(5) + '</td>';
      for (var h = 0; h < 24; h++) {
        var count = grid[day][h];
        var bg = cellColor(count, maxCount);
        var tip = count > 0 ? count + ' spot' + (count > 1 ? 's' : '') : '';
        html += '<td class="act-cell" style="background:' + bg + '" title="' + tip + '"></td>';
      }
      html += '</tr>';
    });

    html += '</tbody></table>';
    heatmapEl.innerHTML = html;
  }

  // ── Band checkboxes ───────────────────────────────────────────────
  function renderBands() {
    var colorMap = (window.PskUi && window.PskUi.COLOR_MAP) || {};
    var html = '';
    ALL_BANDS.forEach(function (b) {
      var color = colorMap[b] || '#888';
      var checked = (!selectedBands || selectedBands.indexOf(b) !== -1) ? ' checked' : '';
      html += '<label class="act-band-label">' +
              '<input type="checkbox" class="act-band-cb" data-band="' + b + '"' + checked + '>' +
              '<span class="act-band-dot" style="background:' + color + '"></span>' +
              b + 'm</label>';
    });
    bandsEl.innerHTML = html;

    bandsEl.querySelectorAll('.act-band-cb').forEach(function (cb) {
      cb.addEventListener('change', function () {
        var checked = Array.prototype.slice.call(bandsEl.querySelectorAll('.act-band-cb:checked'));
        selectedBands = checked.length === ALL_BANDS.length
          ? null
          : checked.map(function (c) { return parseInt(c.dataset.band, 10); });
        renderHeatmap();
      });
    });
  }

  // ── Fetch & render ────────────────────────────────────────────────
  function fetchAndRender() {
    if (!currentCallsign) return;
    heatmapEl.innerHTML = '<div class="act-loading">Loading…</div>';
    var callsigns = currentCallsign.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    fetch('/api/dxpedition_activity?callsign=' + encodeURIComponent(callsigns.join(',')))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        activityData = data;
        renderHeatmap();
      })
      .catch(function () {
        heatmapEl.innerHTML = '<div class="act-loading">Failed to load activity.</div>';
      });
  }

  // ── Drag ──────────────────────────────────────────────────────────
  function initDrag() {
    var dragging = false;
    var ox = 0, oy = 0;

    titleBar.addEventListener('mousedown', function (e) {
      if (e.target.tagName === 'BUTTON') return;
      dragging = true;
      ox = e.clientX - dialog.offsetLeft;
      oy = e.clientY - dialog.offsetTop;
      e.preventDefault();
    });

    document.addEventListener('mousemove', function (e) {
      if (!dragging) return;
      dialog.style.right = 'auto';
      dialog.style.left = (e.clientX - ox) + 'px';
      dialog.style.top  = (e.clientY - oy) + 'px';
    });

    document.addEventListener('mouseup', function () { dragging = false; });
  }

  // ── Public API ────────────────────────────────────────────────────
  function init() {
    dialog    = document.getElementById('activityDialog');
    titleBar  = document.getElementById('activityDialogTitleBar');
    titleText = document.getElementById('activityDialogTitleText');
    heatmapEl = document.getElementById('activityDialogHeatmap');
    bandsEl   = document.getElementById('activityDialogBands');

    document.getElementById('activityDialogClose')
      .addEventListener('click', close);
    document.getElementById('activityDialogRefresh')
      .addEventListener('click', fetchAndRender);

    initDrag();
  }

  function open(callsign) {
    currentCallsign = callsign;
    selectedBands = null;

    var labels = callsign.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    titleText.textContent = labels.join(' / ') + ' — 7-day Activity (UTC)';

    dialog.style.display = 'flex';
    renderBands();
    fetchAndRender();
  }

  function close() {
    if (dialog) dialog.style.display = 'none';
    currentCallsign = '';
    activityData = [];
  }

  window.PskActivityDialog = { init: init, open: open, close: close };
})();
