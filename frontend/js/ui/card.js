// card({ title, status, body, footer, className }) -> the .card of css/components.css with an optional header (title and a status badge),
// a body and an optional footer. `body` and `footer` are lists of nodes or strings; text is never set as HTML.
import { element } from '../dom.js';

const section = (className, children) => {
  const node = element('div', '', className);
  node.append(...children);
  return node;
};

export function card({ title = '', status = null, body = [], footer = [], className = '' } = {}) {
  const box = element('div', '', className ? `card ${className}` : 'card');
  if (title || status) box.append(section('card-header', [...(title ? [element('h2', title)] : []), ...(status ? [status] : [])]));
  box.append(section('card-body', body));
  if (footer.length) box.append(section('card-footer', footer));
  return box;
}
