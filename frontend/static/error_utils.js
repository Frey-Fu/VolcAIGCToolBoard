window.ErrorUtils = {
  extractUpstream: function (result, raw) {
    var upstream = null;
    if (result && typeof result.upstream_error === 'object') upstream = result.upstream_error;
    else if (result && typeof result.error === 'object') upstream = result.error;
    var rawText = (result && result.error_response_content) ? result.error_response_content : (raw || '');
    var rid = '';
    try {
      var parsedRaw = rawText ? JSON.parse(rawText) : null;
      rid = (parsedRaw && parsedRaw.error && (parsedRaw.error.request_id || parsedRaw.request_id)) || '';
    } catch (e) {}
    return {
      code: upstream && upstream.code || '',
      type: upstream && upstream.type || '',
      message: upstream && upstream.message || '',
      request_id: rid,
      raw: rawText
    };
  },
  renderError: function (containerId, title, baseError, upstreamInfo) {
    var resultContent = document.getElementById(containerId);
    var resultDiv = resultContent ? resultContent.parentElement : null;
    if (resultDiv) resultDiv.style.display = 'block';
    if (!resultContent) return;
    var structured = '';
    if (upstreamInfo && (upstreamInfo.code || upstreamInfo.type || upstreamInfo.message || upstreamInfo.request_id)) {
      structured = '<div class="status-detail">错误码: ' + (upstreamInfo.code || '') + (upstreamInfo.type ? ' | 类型: ' + upstreamInfo.type : '') + '</div>' +
                  '<div class="status-detail">错误原因: ' + (upstreamInfo.message || '') + '</div>' +
                  (upstreamInfo.request_id ? '<div class="status-detail">Request id: ' + upstreamInfo.request_id + '</div>' : '');
    }
    var rawBlock = upstreamInfo && upstreamInfo.raw ? '<div style="margin-top:8px;">错误响应内容：</div><pre style="white-space:pre-wrap; word-break:break-word; background:#fff; border:1px solid #eee; padding:10px; border-radius:6px;">' + upstreamInfo.raw + '</pre>' : '';
    resultContent.innerHTML = '<div class="status-box" style="border-left-color:#dc3545;">' +
      '<div class="status-text" style="color:#dc3545;">' + title + '</div>' +
      '<div class="status-detail">' + baseError + '</div>' +
      structured + rawBlock +
    '</div>';
  }
};