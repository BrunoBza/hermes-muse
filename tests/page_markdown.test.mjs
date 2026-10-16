// Run: node --test tests/page_markdown.test.mjs (no Hermes or React needed).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source = readFileSync(new URL('../ui/page.js', import.meta.url), 'utf8');
const {museMarkdown, museBody} = new Function(source + '\nreturn {museMarkdown, museBody};')();
const h = (tag, props, ...children) => ({tag, props, children: children.flat(Infinity)});
const render = text => museMarkdown(h, text);
const walk = (nodes, found = []) => {
  for (const n of [nodes].flat(Infinity)) if (n && typeof n === 'object') { found.push(n); walk(n.children, found); }
  return found;
};
const tags = text => walk(render(text)).map(n => n.tag);

test('renders headings, lists, quotes, code and tables', () => {
  const t = tags('# A\n\n- one\n  - two\n1. x\n\n> quote\n\n```js\n<b>raw</b>\n```\n\n| a | b |\n| - | - |\n| 1 | 2 |');
  for (const tag of ['h1', 'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'table', 'th', 'td']) assert.ok(t.includes(tag), tag);
  assert.equal(t.filter(x => x === 'ul').length, 2, 'nested list');
});

test('never creates elements from raw HTML', () => {
  const nodes = walk(render('<script>alert(1)</script> <img src=x onerror=alert(1)> **ok**'));
  assert.deepEqual([...new Set(nodes.map(n => n.tag))].sort(), ['p', 'strong']);
  assert.ok(nodes.some(n => n.children.includes('<script>alert(1)</script> <img src=x onerror=alert(1)> ')));
});

test('links: http(s) open safely in a new window, other schemes stay text', () => {
  const links = walk(render('[a](https://x.test) [b](javascript:alert(1)) [c](data:text/html,x) ![i](https://x.test/i.png) https://y.test/z')).filter(n => n.tag === 'a');
  assert.equal(links.length, 3);
  for (const a of links) assert.deepEqual([a.props.target, a.props.rel], ['_blank', 'noopener noreferrer']);
  assert.ok(links.every(a => a.props.href.startsWith('https://')));
});

test('feed body drops the stored title and trailing Sources list only', () => {
  const body = '# T\n\nText\n\n## Sources\n- https://a.test\n- note';
  assert.equal(museBody(body, 'T', true), 'Text');
  assert.equal(museBody(body, 'T', false), 'Text\n\n## Sources\n- https://a.test\n- note');
  assert.equal(museBody('Keep\n\n## Sources\nprose here', 'T', true), 'Keep\n\n## Sources\nprose here');
});
