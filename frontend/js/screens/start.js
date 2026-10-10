import { getBuiltins, getLanAddress } from '../api.js';
import { renderPlaceholder } from './placeholder.js';

// Placeholder: the real screen replaces this body. render(root, params) is called by router.js.
export function render(root) {
  return renderPlaceholder(root, {
    title: 'Start',
    description: 'Pick an instrument and begin a session.',
    calls: [
      { label: 'GET /builtins', run: () => getBuiltins('violin') },
      { label: 'GET /lan-address', run: () => getLanAddress() },
    ],
  });
}
