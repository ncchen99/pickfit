// Colours for the video, taken from the live site (worker/src/ui/styles.ts, light scheme)
// and Fitz's own palette (brand/mascot/build.py). Fitz's colours are never changed.

export const site = {
  paper: '#F7F7F4',
  raised: '#FFFFFF',
  voice: '#F1F6E2',
  voiceLine: '#CDD7AB',
  voiceEdge: '#A9B77E',
  sunk: '#F0F1EC',
  rule: '#DEDFD9',
  lineCtl: '#80817A',
  ink: '#1A1D17',
  ink2: '#4F5149',
  ink3: '#65655E',
  tape: '#F5C243',
  tapeEdge: '#A57710',
  tapeDeep: '#D9A21B',
  tapeInk: '#3A2905',
  tapeTab: '#C3CAD2',
  stitch: '#C4552D',
  fitzLine: '#4A2E22',
  pass: '#2E7A35',
  caution: '#8A5300',
  fail: '#B23A26',
  info: '#28698A',
};

export const fitz = {
  ink: '#4A2E22',
  body: '#A9BC4C',
  wing: '#869E3A',
  tail: '#7C9334',
  cap: '#C4552D',
  belly: '#FFF3D3',
  beak: '#F0A04B',
  beakTop: '#CF6F2A',
  tape: '#F5C243',
  metal: '#C3CAD2',
  blush: '#F2917C',
  white: '#FFFFFF',
  leaf: '#6CBF4E',
  leafDark: '#3E8A3A',
  box: '#E8BC7E',
  boxDark: '#C9924E',
};

// The site's two curves and its durations (styles.ts), in GSAP form.
export const ease = {
  out: 'expo.out', // closest GSAP preset to cubic-bezier(.16,1,.3,1)
  io: 'power3.inOut', // cubic-bezier(.65,0,.35,1)
};

export const fonts = {
  display: '"Bricolage Display", "Bricolage Grotesque", ui-sans-serif, system-ui, sans-serif', // opsz 96 instance, as the site's Display role
  sans: 'system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif',
  mono: 'ui-monospace, "SF Mono", Menlo, monospace',
};
