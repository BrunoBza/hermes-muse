// Run: node --test tests/page_markdown.test.mjs (no Hermes or React needed).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source = readFileSync(new URL('../ui/page.js', import.meta.url), 'utf8');
const {museMarkdown, museBody, museSource} = new Function(source + '\nreturn {museMarkdown, museBody, museSource};')();
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

test('a leading H1 that repeats or extends the title is dropped, a different one is kept', () => {
  assert.equal(museBody('# Standing desk: a comparison\n\nText', 'Standing desk', false), 'Text');
  assert.equal(museBody('\n# standing  DESK\n\nText', 'Standing desk', false), 'Text');
  assert.equal(museBody('# Standing desk\n\n# Standing desk\n\nText', 'Standing desk', false), 'Text', 'stored title plus body title');
  assert.equal(museBody('# Something else entirely\n\nText', 'Standing desk', false), '# Something else entirely\n\nText');
});

test('sources show domain plus path as a safe link; non-URLs stay text', () => {
  const [domain, path] = museSource(h, 'https://www.example.com/a/b?q=1', 's');
  assert.deepEqual([domain.tag, domain.children[0], domain.props.href, domain.props.rel], ['a', 'example.com', 'https://www.example.com/a/b?q=1', 'noopener noreferrer']);
  assert.equal(path.children[0], ' /a/b?q=1');
  assert.equal(museSource(h, 'fixture:private-note', 's'), 'fixture:private-note');
  assert.equal(museSource(h, 'javascript:alert(1)', 's'), 'javascript:alert(1)');
});
