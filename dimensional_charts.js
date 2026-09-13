(function (global) {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const COLORS = [
    ['#bf8cff', '#7736f0', '#341164', '#e8d4ff'],
    ['#69f2ff', '#0ca9df', '#075070', '#d7fdff'],
    ['#ff92d5', '#ea388f', '#730f45', '#ffe1f2'],
    ['#ffcc76', '#f47a29', '#7f3116', '#fff0c9'],
    ['#9ba8ff', '#5962e8', '#27256c', '#e2e5ff'],
    ['#69f0d1', '#12bda3', '#075c54', '#cefff1'],
    ['#ec96ff', '#ad3de8', '#551b70', '#f9ddff'],
    ['#ffe47c', '#ddb42c', '#685114', '#fff7ce']
  ];
  let serial = 0;
  const number = new Intl.NumberFormat(undefined, { maximumSignificantDigits: 10 });
  const compact = new Intl.NumberFormat(undefined, { notation: 'compact', maximumSignificantDigits: 3 });
  const scientific = new Intl.NumberFormat(undefined, { notation: 'scientific', maximumSignificantDigits: 6 });
  function valueText(value) {
    return value !== 0 && (value < .000001 || value >= 1e12) ? scientific.format(value) : number.format(value);
  }
  function tickText(value) {
    if (value !== 0 && (value < .01 || value >= 1e9)) return scientific.format(value);
    return value >= 1000 ? compact.format(value) : number.format(value);
  }
  function html(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function svg(tag, attrs, parent) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs || {}).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (parent) parent.appendChild(node);
    return node;
  }
  function gradient(defs, id, stops, horizontal) {
    const node = svg('linearGradient', { id, x1: '0%', y1: '0%', x2: horizontal ? '100%' : '0%', y2: horizontal ? '0%' : '100%' }, defs);
    stops.forEach(([offset, color, opacity]) => svg('stop', { offset, 'stop-color': color, 'stop-opacity': opacity === undefined ? 1 : opacity }, node));
    return 'url(#' + id + ')';
  }

  /** Replace container contents. Keeps caller row order; never invents numeric data. */
  function renderDimensionalBars(container, options) {
    if (!container || typeof container.replaceChildren !== 'function') throw new TypeError('A DOM container is required.');
    const input = options || {};
    const source = Array.isArray(input.rows) ? input.rows : [];
    const seen = new Set();
    const valid = [];
    let omitted = 0;
    source.forEach(row => {
      const idOkay = row && ((typeof row.id === 'string' && row.id.trim()) || (typeof row.id === 'number' && Number.isFinite(row.id)));
      if (!idOkay || seen.has(row.id) || typeof row.name !== 'string' || !row.name.trim() || typeof row.value !== 'number' || !Number.isFinite(row.value) || row.value < 0) {
        omitted += 1;
        return;
      }
      seen.add(row.id);
      valid.push({ id: row.id, name: row.name, value: row.value, label: typeof row.label === 'string' && row.label.trim() ? row.label : valueText(row.value) });
    });
    const rows = valid.slice(0, 8);
    const uid = 'sb3d-' + (++serial);
    const label = typeof input.label === 'string' && input.label.trim() ? input.label : 'Comparison';
    const figure = html('figure', 'sb3d');
    const caption = html('figcaption', 'sb3d-heading', label);
    caption.id = uid + '-title';
    figure.setAttribute('aria-labelledby', caption.id);
    figure.appendChild(caption);
    const selectable = typeof input.onSelect === 'function';
    const description = html('p', 'sb3d-description', rows.length ? (selectable ? 'Select a '+(input.itemName || 'person')+' to see the details.' : 'Values share the same scale and start at zero.') : 'No values to compare yet.');
    figure.appendChild(description);
    container.replaceChildren(figure);
    if (!rows.length) {
      figure.appendChild(html('div', 'sb3d-empty', 'Add data to see this comparison.'));
    } else {
      const width = Math.max(380, 94 + rows.length * 104);
      const height = 390;
      const base = 270;
      const plotHeight = 206;
      const depth = { x: 22, y: 16 };
      const actualMaximum = Math.max(...rows.map(row => row.value));
      const maximum = typeof input.maxValue === 'number' && Number.isFinite(input.maxValue) ? Math.max(actualMaximum, input.maxValue) : actualMaximum;
      const scroller = html('div', 'sb3d-scroll');
      scroller.setAttribute('role', 'region');
      scroller.setAttribute('aria-label', label + ' chart; scroll horizontally when needed');
      scroller.tabIndex = 0;
      const scene = html('div', 'sb3d-scene');
      scene.style.width = width + 'px';
      scene.style.height = height + 'px';
      scene.style.setProperty('--sb3d-baseline', base + 'px');
      const art = svg('svg', { viewBox: '0 0 ' + width + ' ' + height, width, height, 'aria-hidden': 'true', focusable: 'false', class: 'sb3d-art' });
      const defs = svg('defs', {}, art);
      const floor = gradient(defs, uid + '-floor', [['0%', '#2b275c', .6], ['100%', '#10142b', 0]]);
      const glow = svg('radialGradient', { id: uid + '-glow' }, defs);
      svg('stop', { offset: '0%', 'stop-color': '#726bff', 'stop-opacity': '.19' }, glow);
      svg('stop', { offset: '100%', 'stop-color': '#726bff', 'stop-opacity': '0' }, glow);
      svg('ellipse', { cx: width / 2, cy: 212, rx: width * .52, ry: 178, fill: 'url(#' + uid + '-glow)' }, art);
      svg('path', { d: 'M44 ' + base + ' H' + (width - 14) + ' L' + (width + 48) + ' 365 H0 Z', fill: floor }, art);
      [0, .5, 1].forEach(ratio => {
        const y = base - ratio * plotHeight;
        svg('line', { x1: 45, x2: width - 20, y1: y, y2: y, stroke: ratio === 0 ? '#aaa7e2' : '#8484ae', 'stroke-opacity': ratio === 0 ? '.45' : '.16', 'stroke-dasharray': ratio === 0 ? '0' : '3 7' }, art);
        if (maximum > 0 || ratio === 0) {
          const tick = svg('text', { x: 34, y: y + 4, fill: '#b1b8d6', 'font-size': 11, 'text-anchor': 'end' }, art);
          tick.textContent = tickText(maximum * ratio);
        }
      });
      for (let x = 54; x < width; x += 76) svg('line', { x1: x, y1: base, x2: x + (x - width / 2) * .28, y2: 356, stroke: '#9999df', 'stroke-opacity': '.09' }, art);
      [286, 310, 345].forEach(y => svg('line', { x1: 20, x2: width - 6, y1: y, y2: y, stroke: '#9999df', 'stroke-opacity': '.08' }, art));
      const mask = svg('mask', { id: uid + '-reflection', maskUnits: 'userSpaceOnUse', x: 0, y: base + 2, width, height: 59 }, defs);
      const fade = gradient(defs, uid + '-fade', [['0%', '#fff', .36], ['100%', '#000', 0]]);
      svg('rect', { x: 0, y: base + 2, width, height: 59, fill: fade }, mask);
      const columnWidth = (width - 82) / rows.length;
      const buttons = [];
      rows.forEach((row, index) => {
        const colors = COLORS[index];
        const x = 62 + index * columnWidth + (columnWidth - 60) / 2 - 11;
        const barHeight = maximum === 0 ? 0 : row.value / maximum * plotHeight;
        const y = base - barHeight;
        const group = svg('g', { class: 'sb3d-bar', 'data-value': row.value, 'data-front-height': barHeight }, art);
        if (row.value > 0) {
          const front = gradient(defs, uid + '-front-' + index, [['0%', colors[0]], ['44%', colors[1]], ['100%', colors[2]]]);
          const side = gradient(defs, uid + '-side-' + index, [['0%', colors[2]], ['100%', colors[1]]], true);
          svg('ellipse', { cx: x + 27, cy: base + 4, rx: 34, ry: 6, fill: colors[1], opacity: '.15' }, art);
          svg('polygon', { points: [[x + 60, y], [x + 82, y - depth.y], [x + 82, base - depth.y], [x + 60, base]].map(p => p.join(',')).join(' '), fill: side, class: 'sb3d-side' }, group);
          svg('rect', { x, y, width: 60, height: barHeight, fill: front, class: 'sb3d-front' }, group);
          svg('polygon', { points: [[x, y], [x + depth.x, y - depth.y], [x + 82, y - depth.y], [x + 60, y]].map(p => p.join(',')).join(' '), fill: colors[3], class: 'sb3d-top' }, group);
          svg('rect', { x: x + 3, y: y + Math.min(3, barHeight / 3), width: 2, height: Math.max(0, barHeight - 6), fill: '#fff', opacity: '.24' }, group);
          svg('line', { x1: x, x2: x + 60, y1: y, y2: y, stroke: '#fff', 'stroke-opacity': '.55' }, group);
          const reflection = svg('g', { mask: 'url(#' + uid + '-reflection)' }, art);
          const reflected = group.cloneNode(true);
          reflected.removeAttribute('data-value');
          reflected.removeAttribute('data-front-height');
          reflected.setAttribute('class', 'sb3d-reflected');
          reflected.setAttribute('transform', 'translate(0 ' + (2 * base + 3) + ') scale(1 -1)');
          reflection.appendChild(reflected);
        } else {
          svg('line', { x1: x, x2: x + 60, y1: base, y2: base, stroke: colors[0], 'stroke-width': 2, class: 'sb3d-zero' }, group);
        }
        const button = html(selectable ? 'button' : 'div', 'sb3d-column');
        button.style.left = (54 + index * columnWidth) + 'px';
        button.style.width = columnWidth + 'px';
        button.style.setProperty('--sb3d-color', colors[0]);
        button.style.setProperty('--sb3d-value-top', Math.max(16, y - depth.y - 35) + 'px');
        button.setAttribute('aria-label', row.name + ': ' + row.label);
        button.title = row.name + ': ' + row.label;
        if (selectable) {
          button.type = 'button';
          button.setAttribute('aria-pressed', 'false');
          button.addEventListener('click', () => {
            buttons.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
            input.onSelect(row.id);
          });
          buttons.push(button);
        }
        button.appendChild(html('span', 'sb3d-value', row.label));
        button.appendChild(html('span', 'sb3d-name', row.name));
        scene.appendChild(button);
      });
      scene.prepend(art);
      scroller.appendChild(scene);
      figure.appendChild(scroller);
      figure.appendChild(html('p', 'sb3d-footnote', 'Zero baseline' + (selectable ? ' · Tab to a '+(input.itemName || 'person')+', then press Enter or Space' : '') + ' · Scroll to see all columns'));
    }
    if (omitted || valid.length > rows.length) {
      const notices = [];
      if (omitted) notices.push(omitted + ' invalid or duplicate row' + (omitted === 1 ? '' : 's') + ' omitted.');
      if (valid.length > rows.length) notices.push('Showing the first 8 of ' + valid.length + ' valid rows.');
      figure.appendChild(html('p', 'sb3d-notice', notices.join(' ')));
    }
    return { element: figure, rowsRendered: rows.length, omittedRows: omitted, destroy() { if (figure.parentNode === container) figure.remove(); } };
  }
  global.ShiftBriefCharts = Object.freeze({ renderDimensionalBars });
})(window);
