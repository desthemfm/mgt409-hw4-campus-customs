// Game Day settings (Problem 10). One place to change the date, the kit, and the picks.
//
// KICKOFF is a setting, not live data: Saturday, Nov 21, 2026, 12:00 PM Eastern,
// confirmed by the site owner on Oct 22, 2026. Change this one line if it ever moves.
export const GAME_DAY = {
  kickoff: new Date('2026-11-21T12:00:00-05:00'),
  // How long after kickoff the "It's Game Day" message stays up before the home page
  // switches to its everyday headline.
  showForHoursAfter: 30,
}

// The game-day kit: three pieces for the stands, added to the cart together.
export const KIT_IDS = ['2025-yale-vs-harvard-t-shirt', 'basic-hoodie-big-yale', 'super-heavyweight-crewneck-arched-yale-crest']

// "More for the stands": football and Yale Bowl pieces.
export const STANDS_IDS = ['yale-bowl-t-shirt', 'tri-blend-sports-football-t-shirt', 'football-left-chest-t-shirt', 'champion-reverse-weave-crewneck']

export type GamePhase = 'countdown' | 'gameday' | 'after'

export function gamePhase(now = Date.now()): GamePhase {
  const k = GAME_DAY.kickoff.getTime()
  if (now < k) return 'countdown'
  if (now < k + GAME_DAY.showForHoursAfter * 3600_000) return 'gameday'
  return 'after'
}
