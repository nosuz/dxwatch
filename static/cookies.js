(function () {
  function getCookie(name) {
    const escaped = name.replace(/([.$?*|{}()\[\]\\+^])/g, '\\$1');
    const match = document.cookie.match(new RegExp('(?:^|; )' + escaped + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : '';
  }

  function setCookie(name, value, days) {
    const maxAge = days ? ('; max-age=' + (days * 24 * 60 * 60)) : '';
    document.cookie = name + '=' + encodeURIComponent(value) + maxAge + '; path=/; samesite=lax';
  }

  window.PskCookies = { getCookie, setCookie };
})();
