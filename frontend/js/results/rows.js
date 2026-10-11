// A closed, tap-to-open row (the shared .disclosure rule in css/components.css): a 44px title line, the parts under it once opened.
import { element } from '../dom.js';

export function disclosureRow(title, className, parts) {
  const row = element('details', '', `disclosure ${className}`);
  row.append(element('summary', title), ...parts);
  return row;
}
