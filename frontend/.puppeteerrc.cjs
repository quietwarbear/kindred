/**
 * Keep puppeteer's Chrome inside node_modules/.cache so Vercel's build cache
 * persists it between deploys (default ~/.cache is not cached there).
 */
const { join } = require('path');

module.exports = {
  cacheDirectory: join(__dirname, 'node_modules', '.cache', 'puppeteer'),
};
