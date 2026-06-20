/**
 * i18n.js — QHI Tracker 国际化（兜底文件）
 * 
 * 如果后端已提供 i18n.js，本文件作为补充翻译加载。
 * 通过 __i18n 全局对象提供 t() / applyI18n() / toggleLang() / getLang() 接口。
 */
(function() {
  if (window.__i18n && window.__i18n._initialized) return;

  // 默认翻译表
  var translations = {
    zh: {
      // ----- 新增：小票打印 -----
      'th.action': '操作',
      'btn.printReceipt': '打印小票',
      'msg.printSent': '小票已发送到打印机',
      'msg.receiptPDF': 'XP-80 不在线，小票 PDF 已生成',
      'msg.printFailed': '打印失败',
      'msg.printTimeout': '打印请求超时',
      'msg.networkError': '网络连接错误',
    },
    en: {
      'th.action': 'Action',
      'btn.printReceipt': 'Print Receipt',
      'msg.printSent': 'Receipt sent to printer',
      'msg.receiptPDF': 'XP-80 offline, receipt PDF generated',
      'msg.printFailed': 'Print failed',
      'msg.printTimeout': 'Print request timeout',
      'msg.networkError': 'Network error',
    }
  };

  var currentLang = (navigator.language || 'zh-CN').startsWith('en') ? 'en' : 'zh';

  function t(key) {
    var tbl = translations[currentLang];
    if (tbl && tbl[key]) return tbl[key];
    // 如果已有后端 __i18n，委托给它
    if (window.__i18n && window.__i18n !== _i18n) return window.__i18n.t(key);
    // 回退：直接返回键名（中文环境直接显示键名，通常已是中文）
    return key;
  }

  function applyI18n() {
    var els = document.querySelectorAll('[data-i18n]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var key = el.getAttribute('data-i18n');
      var text = t(key);
      if (text !== key) {
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
          el.placeholder = text;
        } else {
          el.textContent = text;
        }
      }
    }
  }

  function toggleLang() {
    currentLang = currentLang === 'zh' ? 'en' : 'zh';
    document.getElementById('langToggle').textContent = currentLang === 'zh' ? 'EN' : '中文';
    applyI18n();
    // 触发自定义事件通知其他脚本
    document.dispatchEvent(new CustomEvent('langchange'));
    try { localStorage.setItem('qhi_lang', currentLang); } catch(e) {}
  }

  function getLang() {
    return currentLang === 'zh' ? 'zh-CN' : 'en-US';
  }

  var _i18n = {
    t: t,
    applyI18n: applyI18n,
    toggleLang: toggleLang,
    getLang: getLang,
    _initialized: true
  };

  // 合并到现有 __i18n 或直接赋值
  if (window.__i18n) {
    // 已有后端 i18n，仅扩展现有对象（不覆盖已有函数）
    var orig_t = window.__i18n.t;
    window.__i18n.t = function(key) {
      var val = t(key);
      if (val === key && orig_t !== t) return orig_t(key);
      return val;
    };
  } else {
    window.__i18n = _i18n;
  }

  // 从 localStorage 恢复语言设置
  try {
    var saved = localStorage.getItem('qhi_lang');
    if (saved && (saved === 'en' || saved === 'zh')) currentLang = saved;
  } catch(e) {}

  // 立即应用翻译
  document.addEventListener('DOMContentLoaded', applyI18n);
  if (document.readyState !== 'loading') applyI18n();
})();
