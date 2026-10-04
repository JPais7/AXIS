import { test, expect } from '@playwright/test';

// Synthetic demonstration database (separate server). Never the production database.
const SYNTHETIC = process.env.AXIS_SYNTHETIC_URL || 'http://127.0.0.1:8766';
const PRODUCTION = process.env.AXIS_WORKSPACE_URL || 'http://127.0.0.1:8765';
const project = '/projects/AXIS-DD-ERAP1-CURATED-001';

for (const width of [1440, 1024]) {
  test(`synthetic experimental-results loop ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const errors = [];
    const remote = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => { if (!r.url().startsWith('http://127.0.0.1:')) remote.push(r.url()); });
    const shot = async name => page.screenshot({ path: `test-results/results-${width}-${name}.png` });
    const heading = async (name, level = 2) => { const h = page.getByRole('heading', { name, exact: true, level }); await h.scrollIntoViewIfNeeded(); return h; };

    await page.goto(`${SYNTHETIC}${project}/results`);
    await expect(page.getByRole('heading', { name: 'Experiments / Results', exact: true, level: 1 })).toBeVisible();
    await expect(page.locator('.proposal-banner.synthetic').first()).toContainText('SYNTHETIC DEMONSTRATION');
    await expect(page.locator('.proposal-banner.synthetic').first()).toContainText('Synthetic test fixture — not real experimental evidence');
    await expect(page.locator('main, #main').first()).toContainText('Proposal, performance, observation, interpretation, review and decision are separate objects');
    await shot('1-experiments-overview');
    await heading('Results');
    await expect(page.locator('table caption').first()).toContainText('Results and their interpretations');
    await expect(page.getByText('SYNTHETIC').first()).toBeVisible();
    await shot('2-results-ledger');
    await heading('Decision timeline');
    await expect(page.locator('.timeline')).toContainText('DecisionState v1');
    await expect(page.locator('.timeline')).toContainText('DecisionState v4');
    await expect(page.locator('.timeline')).toContainText('accepted with caveat');
    await shot('3-decision-timeline');

    // performed experiment detail
    await page.getByRole('button', { name: 'Inspect execution, deviations and QC' }).first().click();
    await expect(page.getByRole('dialog')).toContainText('Actual execution');
    await expect(page.getByRole('dialog')).toContainText('Design (proposal)');
    await shot('4-performed-experiment-detail');
    await page.keyboard.press('Escape');

    // accepted result: observed vs interpreted vs review, scenario match, QC, artifacts
    await page.getByRole('button', { name: 'synthetic:res:engagement-maben3@v1' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText('OBSERVED');
    await expect(dialog).toContainText('INTERPRETATION');
    await expect(dialog).toContainText('(not an observation)');
    await expect(dialog).toContainText('Observed result ↕ expected scenario');
    await expect(dialog).toContainText('decision:exp:engagement-assay:s1');
    await expect(dialog).toContainText('accepted with caveat');
    await expect(dialog).toContainText('sha256');
    await shot('5-result-observed-vs-interpreted');
    await dialog.getByText('Observed result ↕ expected scenario').scrollIntoViewIfNeeded();
    await shot('6-scenario-match');
    await dialog.getByRole('heading', { name: 'Quality control' }).scrollIntoViewIfNeeded();
    await shot('7-qc-state');
    await page.keyboard.press('Escape');

    // non-interpretable and unexpected
    await page.getByRole('button', { name: 'synthetic:res:failed-maben2@v1' }).click();
    await expect(page.getByRole('dialog')).toContainText('non interpretable');
    await expect(page.getByRole('dialog')).toContainText('ineligible qc failure');
    await shot('8-non-interpretable-result');
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'synthetic:res:unexpected-maben1@v1' }).click();
    await expect(page.getByRole('dialog')).toContainText('outside predefined scenarios');
    await expect(page.getByRole('dialog')).toContainText('nothing was force-fitted');
    await page.getByRole('button', { name: 'Preview decision impact if accepted' }).click();
    await expect(page.locator('#impact-preview')).toContainText('Preview — not current decision');
    await expect(page.locator('#impact-preview')).toContainText('not stored, not the current decision');
    await page.locator('#impact-preview').scrollIntoViewIfNeeded();
    await shot('9-unexpected-result-and-impact-preview');
    await page.keyboard.press('Escape');

    // review queue
    await page.goto(`${SYNTHETIC}${project}/review`);
    await expect(page.getByRole('heading', { name: 'Scientific review', exact: true, level: 1 })).toBeVisible();
    await expect(page.locator('main, #main').first()).toContainText('never resolved by majority');
    await expect(page.locator('main, #main').first()).toContainText('84 pending of 84');
    await heading('Review conflicts');
    await expect(page.locator('#conflicts ~ ul').first()).toContainText('synthetic:int:disputed-maben1');
    await shot('10-review-queue-and-conflict');
    await heading('Scenario → explanation mappings');
    await shot('11-scenario-mapping-review');

    // decision v3 with scope breakdown, results and causal diff
    await page.goto(`${SYNTHETIC}${project}/decision`);
    await expect(page.locator('.proposal-banner.synthetic').first()).toContainText('SYNTHETIC DEMONSTRATION');
    await expect(page.locator('main, #main').first()).toContainText('Decision state v4');
    await heading('Engagement by scope', 3);
    const table = page.locator('table').filter({ hasText: 'Direct cellular engagement per scope' });
    await expect(table).toContainText('compound:maben-3');
    await expect(table).toContainText('compound:maben-2');
    await expect(table).toContainText('perturbagen: DG013A');
    await expect(page.getByText('A result resolves only its own compound')).toBeVisible();
    await shot('12-decision-v4-compound-scope');
    await heading('Experimental results informing this decision');
    await shot('13-decision-results');
    await heading('Decision history');
    const history = page.locator('#history ~ article');
    await expect(history.first()).toContainText('Decision state v4');
    await expect(history.first()).toContainText('Did the decision change? Yes');
    await expect(history.first()).toContainText('new experimental evidence');
    await expect(history.first()).toContainText('Critical uncertainty:');
    await expect(history.first()).toContainText('DECISION-RESULT-002');
    await shot('14-causal-diff-decision-changed');
    await expect(history.nth(1)).toContainText('Decision state v3');
    await expect(history.nth(1)).toContainText('review status change');
    await history.nth(1).scrollIntoViewIfNeeded();
    await shot('15-causal-diff-review-change');
    await expect(history.nth(2)).toContainText('new experimental evidence');
    await history.nth(2).scrollIntoViewIfNeeded();
    await shot('16-causal-diff-first-result-partial');

    const semantics = await page.evaluate(() => {
      const levels = [...document.querySelectorAll('h1,h2,h3,h4')].map(h => Number(h.tagName[1]));
      let skip = false;
      for (let i = 1; i < levels.length; i++) if (levels[i] - levels[i - 1] > 1) skip = true;
      const unnamed = [...document.querySelectorAll('button,a[href]')].filter(el => !(el.textContent || '').trim() && !el.getAttribute('aria-label')).length;
      return { skip, unnamed, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
    });
    expect(semantics.skip).toBe(false);
    expect(semantics.unnamed).toBe(0);
    expect(semantics.overflow).toBeLessThanOrEqual(1);
    expect(errors).toEqual([]);
    expect(remote).toEqual([]);
  });
}

test('production ERAP1 stays honest: no result informs the decision and nothing is synthetic', async ({ page }) => {
  await page.goto(`${PRODUCTION}${project}/decision`);
  await expect(page.locator('.proposal-banner.synthetic')).toHaveCount(0);
  await expect(page.locator('main, #main').first()).toContainText('no performed experiment has been imported into it');
  await expect(page.locator('main, #main').first()).toContainText('Pending scientific review');
  await page.goto(`${PRODUCTION}${project}/results`);
  await expect(page.locator('.proposal-banner.synthetic')).toHaveCount(0);
  await expect(page.locator('main, #main').first()).toContainText('No performed experiment has been recorded');
  await expect(page.locator('main, #main').first()).toContainText('No experimental result has been imported');
});

test('review and results pages are keyboard reachable', async ({ page }) => {
  await page.goto(`${SYNTHETIC}${project}/results`);
  const result = page.getByRole('button', { name: 'synthetic:res:engagement-maben3@v1' });
  await result.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toContainText('OBSERVED');
  await page.keyboard.press('Escape');
  await expect(result).toBeFocused();
});
