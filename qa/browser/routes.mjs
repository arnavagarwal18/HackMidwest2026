// The screens to check in each mode. A spec is { name, url (path on the server), stored (the session id kept in localStorage, or null), root, expectedFailures }.
// expected: patterns for failed requests and console errors this screen is meant to produce in that situation (a route the back end does not
// have, an id that does not exist), so they are listed but not counted as bugs.
const APP_ROOT = '#screen';
const REAL_STORAGE_KEY = 'practice_coach_session_id';
const MOCK_STORAGE_KEY = 'practice_coach_session_id_mock';

const spec = (name, url, extra = {}) => ({ name, url, stored: null, root: APP_ROOT, expected: [], ...extra });

export const MOCK_SCREENS = [
  spec('start', '/?mock=1#/start'),
  spec('score', '/?mock=1#/score', { stored: 'sess_unconfirmed' }),
  spec('calibrate', '/?mock=1#/calibrate'),
  spec('take', '/?mock=1#/take'),
  ...['take_1', 'take_mic', 'take_failed', 'take_cant_tell', 'take_fallback', 'take_stuck'].map((id) => spec(`results/${id}`, `/?mock=1#/results/${id}`)),
  ...['ex_1', 'ex_fail', 'ex_not_counted', 'ex_complete', 'ex_done', 'ex_video'].map((id) => spec(`exercise/${id}`, `/?mock=1#/exercise/${id}`)),
  spec('progress', '/?mock=1#/progress'),
  spec('trace/fb_1', '/?mock=1#/trace/fb_1'),
  spec('tone.html?instrument=trumpet', '/tone.html?mock=1&instrument=trumpet', { root: '#tone' }),
  spec('start (stored session is gone)', '/?mock=1#/start', { stored: 'sess_gone' }),
];

const NO_LAN_ADDRESS = [/lan-address/]; // GET /lan-address has no back-end route

export function realScreens(fixtures) {
  const confirmed = { stored: fixtures.sessionId };
  return [
    spec('start', '/#/start'),
    spec('score', '/#/score', { stored: fixtures.unconfirmedSessionId }),
    spec('calibrate', '/#/calibrate', { ...confirmed, expected: NO_LAN_ADDRESS }),
    spec('take', '/#/take', confirmed),
    spec(`results/${fixtures.goodTakeId} (analysed take)`, `/#/results/${fixtures.goodTakeId}`, confirmed),
    spec(`results/${fixtures.failedTakeId} (failed take)`, `/#/results/${fixtures.failedTakeId}`, confirmed),
    spec('results/take_missing (unknown take)', '/#/results/take_missing', { ...confirmed, expected: [/take_missing|find that take/] }),
    spec(`exercise/${fixtures.exerciseId}`, `/#/exercise/${fixtures.exerciseId}`, confirmed),
    spec('exercise/ex_missing (unknown exercise)', '/#/exercise/ex_missing', { ...confirmed, expected: [/ex_missing|find that exercise/] }),
    spec('progress', '/#/progress', confirmed),
    spec(`trace/${fixtures.feedbackId}`, `/#/trace/${fixtures.feedbackId}`, confirmed),
    spec('trace/fb_missing (unknown feedback)', '/#/trace/fb_missing', { ...confirmed, expected: [/fb_missing|find that feedback/] }),
    spec('tone.html?instrument=trumpet', '/tone.html?instrument=trumpet', { root: '#tone' }),
    spec('start (stored session is gone)', '/#/start', { stored: 'no_such_session', expected: [/no_such_session/] }),
  ];
}

export const storageKey = (mode) => (mode === 'mock' ? MOCK_STORAGE_KEY : REAL_STORAGE_KEY);

// Hash routes the nav bar links to, for the rapid-navigation run.
export const NAV_HASHES = {
  mock: ['#/start', '#/score', '#/calibrate', '#/take', '#/results/take_1', '#/exercise/ex_1', '#/progress', '#/trace/fb_1'],
  real: (fixtures) => ['#/start', '#/score', '#/calibrate', '#/take', `#/results/${fixtures.goodTakeId}`, `#/exercise/${fixtures.exerciseId}`, '#/progress', `#/trace/${fixtures.feedbackId}`],
};
