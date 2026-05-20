/* ZBS Stock Research · JS v6.1 */
/* Fixed sidebar scroll spy + Buy signals + Glossary */

(function(){
  'use strict';

  // ── Sidebar smooth scroll ──
  const navLinks = document.querySelectorAll('.nav-item');
  navLinks.forEach(link => {
    link.addEventListener('click', function(e) {
      e.preventDefault();
      const href = this.getAttribute('href');
      if (href && href.startsWith('#')) {
        const target = document.getElementById(href.slice(1));
        if (target) {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }
      // close mobile sidebar
      const sb = document.querySelector('.sidebar');
      const hm = document.querySelector('.ham');
      const ov = document.querySelector('.mob-overlay');
      if (sb) sb.classList.remove('open');
      if (hm) hm.classList.remove('on');
      if (ov) ov.classList.remove('on');
    });
  });

  // ── Sidebar scroll spy ──
  const sections = document.querySelectorAll('.content-section, .hero, .buy-box-wrapper');
  if (navLinks.length && sections.length) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) {
          navLinks.forEach(l => l.classList.remove('active'));
          const id = e.target.id;
          const link = document.querySelector(`.nav-item[href="#${id}"]`);
          if (link) link.classList.add('active');
        }
      });
    }, { rootMargin: '-20% 0px -70% 0px' });
    sections.forEach(s => { if (s.id) observer.observe(s); });
  }

  // ── Hamburger toggle ──
  const ham = document.querySelector('.ham');
  const sidebar = document.querySelector('.sidebar');
  const overlay = document.querySelector('.mob-overlay');
  if (ham && sidebar && overlay) {
    ham.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      ham.classList.toggle('on');
      overlay.classList.toggle('on');
    });
    overlay.addEventListener('click', () => {
      sidebar.classList.remove('open');
      ham.classList.remove('on');
      overlay.classList.remove('on');
    });
  }

  // ── Theme toggle ──
  const themeBtn = document.querySelector('.theme-btn');
  if (themeBtn) {
    themeBtn.addEventListener('click', () => {
      document.body.classList.toggle('light-mode');
    });
  }

  // ── ResizeObserver for ECharts ──
  if (typeof echarts !== 'undefined') {
    const mainEl = document.querySelector('.main') || document.body;
    const ro = new ResizeObserver(() => {
      document.querySelectorAll('[id^="business-pie"],[id^="kline"]').forEach(el => {
        const inst = echarts.getInstanceByDom(el);
        if (inst) inst.resize();
      });
    });
    ro.observe(mainEl);
  }

  // ── Reveal on scroll ──
  const reveals = document.querySelectorAll('.reveal');
  if (reveals.length) {
    const revealObs = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) {
          e.target.classList.add('revealed');
          revealObs.unobserve(e.target);
        }
      });
    }, { threshold: 0.1 });
    reveals.forEach(el => revealObs.observe(el));
  }

  // ── Buy Signal Calculator ──
  window.calcBuySignals = function(klineData) {
    if (!klineData || klineData.length < 20) return null;

    const closes = klineData.map(d => d[1]); // close price
    const highs = klineData.map(d => d[2]);  // high
    const lows = klineData.map(d => d[3]);   // low
    const vols = klineData.map(d => d[5]);   // volume

    // MA calculations
    const ma5 = closes.slice(-5).reduce((a,b) => a+b, 0) / 5;
    const ma10 = closes.slice(-10).reduce((a,b) => a+b, 0) / 10;
    const ma20 = closes.slice(-20).reduce((a,b) => a+b, 0) / 20;

    // RSI (14-period)
    const rsiPeriod = 14;
    let gains = 0, losses = 0;
    for (let i = closes.length - rsiPeriod; i < closes.length; i++) {
      const diff = closes[i] - closes[i-1];
      if (diff > 0) gains += diff;
      else losses -= diff;
    }
    const rsi = losses === 0 ? 100 : 100 - (100 / (1 + gains/losses));

    // MACD
    const ema12 = calcEMA(closes, 12);
    const ema26 = calcEMA(closes, 26);
    const dif = ema12 - ema26;

    // Support levels (recent lows)
    const recentLows = lows.slice(-20);
    const support1 = Math.min(...recentLows);
    const support2 = lows.slice(-60).length >= 60 ? Math.min(...lows.slice(-60)) : support1;

    // Resistance levels (recent highs)
    const recentHighs = highs.slice(-20);
    const resistance1 = Math.max(...recentHighs);

    // Volume trend
    const avgVol5 = vols.slice(-5).reduce((a,b) => a+b, 0) / 5;
    const avgVol20 = vols.slice(-20).reduce((a,b) => a+b, 0) / 20;
    const volRatio = avgVol20 > 0 ? avgVol5 / avgVol20 : 1;

    // Buy signals
    const signals = [
      { name: 'MA5/MA20金叉', on: ma5 > ma20, val: ma5 > ma20 ? 'MA5 > MA20' : 'MA5 < MA20' },
      { name: 'RSI超卖反弹', on: rsi < 40 || (rsi > 30 && rsi < 50), val: 'RSI=' + rsi.toFixed(1) },
      { name: 'MACD金叉', on: dif > 0, val: dif > 0 ? 'DIF>0' : 'DIF<0' },
      { name: '成交量放大', on: volRatio > 1.2, val: '量比=' + volRatio.toFixed(2) },
      { name: '价格在MA20上方', on: closes[closes.length-1] > ma20, val: closes[closes.length-1] > ma20 ? '是' : '否' }
    ];

    const signalCount = signals.filter(s => s.on).length;

    // Buy price suggestion
    const currentPrice = closes[closes.length - 1];
    const buyLow = Math.max(support1 * 1.02, currentPrice * 0.95);
    const buyHigh = Math.min(resistance1 * 0.95, currentPrice * 1.02);
    const stopLoss = support2 * 0.97;
    const target1 = currentPrice * 1.15;
    const target2 = currentPrice * 1.30;

    return {
      currentPrice,
      ma5: ma5.toFixed(2),
      ma10: ma10.toFixed(2),
      ma20: ma20.toFixed(2),
      rsi: rsi.toFixed(1),
      macd: dif.toFixed(4),
      support1: support1.toFixed(2),
      resistance1: resistance1.toFixed(2),
      volRatio: volRatio.toFixed(2),
      buyPrice: buyLow.toFixed(2) + ' - ' + buyHigh.toFixed(2),
      stopLoss: stopLoss.toFixed(2),
      target1: target1.toFixed(2),
      target2: target2.toFixed(2),
      signals,
      signalCount,
      totalSignals: signals.length,
      recommendation: signalCount >= 4 ? '强烈买入' : signalCount >= 3 ? '建议买入' : signalCount >= 2 ? '观望' : '暂不买入'
    };
  };

  function calcEMA(data, period) {
    const k = 2 / (period + 1);
    let ema = data[0];
    for (let i = 1; i < data.length; i++) {
      ema = data[i] * k + ema * (1 - k);
    }
    return ema;
  }

  // ── Render Buy Signals ──
  window.renderBuySignals = function(containerId, klineData) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const signals = calcBuySignals(klineData);
    if (!signals) {
      container.innerHTML = '<p style="color:var(--text-3)">数据不足，无法计算买入信号</p>';
      return;
    }

    container.innerHTML = `
      <div class="buy-grid">
        <div class="buy-item">
          <div class="bi-label">建议买入价</div>
          <div class="bi-value price">${signals.buyPrice}</div>
          <div class="bi-note">当前价 ${signals.currentPrice}</div>
        </div>
        <div class="buy-item">
          <div class="bi-label">止损位</div>
          <div class="bi-value stop">${signals.stopLoss}</div>
          <div class="bi-note">跌破即离场</div>
        </div>
        <div class="buy-item">
          <div class="bi-label">目标价一</div>
          <div class="bi-value target">${signals.target1}</div>
          <div class="bi-note">+15% 止盈</div>
        </div>
        <div class="buy-item">
          <div class="bi-label">目标价二</div>
          <div class="bi-value target">${signals.target2}</div>
          <div class="bi-note">+30% 止盈</div>
        </div>
      </div>
      <div class="buy-signals">
        <div class="bs-title">技术信号监测</div>
        ${signals.signals.map(s => `
          <div class="signal-row">
            <div class="signal-dot ${s.on ? 'on' : 'off'}"></div>
            <div class="signal-name">${s.name}</div>
            <div class="signal-val">${s.val}</div>
          </div>
        `).join('')}
      </div>
      <div class="buy-summary">
        <strong>综合建议：${signals.recommendation}</strong><br>
        技术信号 ${signals.signalCount}/${signals.totalSignals} 满足 ·
        MA5=${signals.ma5} MA20=${signals.ma20} ·
        RSI=${signals.rsi} · 量比=${signals.volRatio}
      </div>
    `;
  };

})();
