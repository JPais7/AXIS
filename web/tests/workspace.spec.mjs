import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const project = '/projects/AXIS-DD-ERAP1-CURATED-001';
const screenshots = '../docs/screenshots/phase2-hardening';
test('protein identity, sequence and snapshot remain separate from disease evidence', async ({ page }) => {
  for (const width of [1440, 1024]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`${project}/protein`);
    await expect(page.getByRole('heading', { name: 'Target / Protein', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: /Q9NZ08 · Endoplasmic/ })).toBeVisible();
    for (const name of ['Gene', 'Protein', 'Isoform', 'Source']) await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
    const structures = page.getByRole('button', { name: /View \d+ imported experimental structure/ });
    if (await structures.count()) await expect(structures).toBeVisible();
    else await expect(page.getByText('No structure records have been imported into AXIS for this target.', { exact: true })).toBeVisible();
    await expect(page.locator('.protein-sequence')).toContainText('941');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    const source = page.getByRole('button', { name: 'UniProt · Q9NZ08 · inspect provenance', exact: true });
    await source.focus();
    await page.keyboard.press('Enter');
    const drawer = page.getByRole('dialog');
    await expect(drawer.getByRole('heading', { name: 'Protein source snapshot', exact: true })).toBeVisible();
    await expect(drawer.getByText('Not reported', { exact: true })).toBeVisible();
    await expect(drawer.getByRole('button', { name: 'Close protein provenance' })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(source).toBeFocused();
    await page.getByRole('link', { name: 'Return to disease evidence →' }).click();
    await expect(page.getByRole('heading', { name: 'Evidence', exact: true })).toBeVisible();
  }
});
test('scientific workspace, evidence drawer and provenance traversal', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${project}/overview`);
  await expect(page.getByRole('heading', { name: 'ERAP1 × Axial Spondyloarthritis', exact: true })).toBeVisible();
  await expect(page.getByText('AI-assisted curation · pending expert review', { exact: true })).toBeVisible();
  await mkdir(screenshots, { recursive: true });
  await page.screenshot({ path: `${screenshots}/overview.png`, fullPage: true });
  await page.getByRole('button', { name: /Human Genetics/ }).click();
  await expect(page.locator('.claims .claim-button')).toHaveCount(2);
  await page.locator('.claims .claim-button').first().click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByRole('heading', { name: 'Context', exact: true })).toBeVisible();
  await expect(drawer.getByText('PMID:21743469', { exact: false }).first()).toBeVisible();
  await page.screenshot({ path: `${screenshots}/evidence-drawer.png`, fullPage: true });
  await drawer.getByRole('button', { name: 'Source → derived claims → project' }).click();
  await expect(drawer.getByRole('heading', { name: 'Claims derived from this source' })).toBeVisible();
  await drawer.locator('.claim-button').first().click();
  await expect(drawer.getByRole('heading', { name: 'Provenance & transformations' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(drawer).not.toBeVisible();
  await page.getByRole('link', { name: 'Mechanism', exact: true }).click();
  await expect(page.locator('.mechanism-edge')).toHaveCount(8);
  await expect(page.locator('.mechanism-edge.hypothesized')).toHaveCount(1);
  await page.screenshot({ path: `${screenshots}/mechanism.png`, fullPage: true });
  await page.locator('.mechanism-edge.hypothesized').click();
  await expect(drawer.getByText('AXIS suggestion — not experimental evidence.', { exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('link', { name: 'Strategies', exact: true }).click();
  await expect(page.locator('.strategy-card')).toHaveCount(4);
  await expect(page.getByText('No assessment classified as contradictory', { exact: false }).first()).toBeVisible();
  await page.screenshot({ path: `${screenshots}/strategies.png`, fullPage: true });
  await page.getByRole('link', { name: 'Open Questions', exact: true }).click();
  await expect(page.getByText('UNRESOLVED SCIENTIFIC QUESTION', { exact: false }).first()).toBeVisible();
  await page.getByRole('link', { name: 'Next Experiment', exact: true }).click();
  await expect(page.locator('.outcomes section')).toHaveCount(14);
  await expect(page.getByText('AXIS SUGGESTION — NOT EXPERIMENTAL EVIDENCE', { exact: false }).first()).toBeVisible();
  await page.screenshot({ path: `${screenshots}/next-experiment.png`, fullPage: true });
  await page.getByRole('link', { name: 'Sources', exact: true }).click();
  await expect(page.locator('.source-card')).toHaveCount(7);
  await page.locator('.source-card').filter({ hasText: 'PMID:26130142' }).click();
  await expect(drawer.getByRole('heading', { name: 'Transformations · package 1.0.0' })).toBeVisible();
  expect(errors).toEqual([]);
});

test('development fixture stays unassessed and keyboard accessible', async ({ page }) => {
  await page.goto('/projects/AXIS-DD-ERAP1-001/overview');
  await expect(page.getByText('Proposal-only development fixture', { exact: true })).toBeVisible();
  await expect(page.locator('.evidence-state.not_assessed')).toHaveCount(5);
  await page.goto(`${project}/evidence`);
  await page.locator('.claims .claim-button').first().focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.locator('.claims .claim-button').first()).toBeFocused();
});

for (const width of [1440, 1024]) {
  test(`context comparison, all scientific pages and layout at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await mkdir(screenshots, { recursive: true });
    for (const route of ['overview', 'evidence', 'mechanism', 'perturbations', 'strategies', 'questions', 'experiments', 'sources']) {
      await page.goto(`${project}/${route}`);
      await expect(page.locator('.scope')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `${screenshots}/${route}-${width}.png`, fullPage: true });
    }
    await page.goto(`${project}/overview`);
    await page.locator('.matrix').screenshot({ path: `${screenshots}/evidence-matrix-${width}.png` });
    await page.goto(`${project}/evidence`);
    for (const suffix of ['C08', 'C12', 'C13']) await page.locator(`[data-select-claim="AXIS-ERAP1-CURATED-${suffix}"]`).check();
    await page.getByRole('button', { name: 'Compare evidence', exact: true }).click();
    const drawer = page.getByRole('dialog');
    await expect(drawer.getByRole('table')).toBeVisible();
    await expect(drawer.getByText('U937', { exact: false }).first()).toBeVisible();
    await expect(drawer.getByText('HeLa', { exact: false }).first()).toBeVisible();
    await expect(drawer.getByRole('button', { name: 'Close evidence drawer' })).toBeFocused();
    await page.screenshot({ path: `${screenshots}/context-comparison-${width}.png` });
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: 'Compare evidence', exact: true })).toBeFocused();
    await page.locator('#main [data-claim="AXIS-ERAP1-CURATED-C12"]').click();
    await expect(drawer.getByRole('heading', { name: 'Context', exact: true })).toBeVisible();
    await page.screenshot({ path: `${screenshots}/drawer-${width}.png` });
    await drawer.getByRole('button', { name: 'Source → derived claims → project' }).click();
    await expect(drawer.getByRole('heading', { name: 'Projects using these claims' })).toBeVisible();
    await page.screenshot({ path: `${screenshots}/source-detail-${width}.png` });
    await drawer.getByRole('link', { name: /AXIS-DD-ERAP1-CURATED-001/ }).click();
    await expect(page.getByRole('heading', { name: 'ERAP1 × Axial Spondyloarthritis', exact: true })).toBeVisible();
  });
}
