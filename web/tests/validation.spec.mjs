import { test, expect } from '@playwright/test';

const project = '/projects/AXIS-DD-ERAP1-CURATED-001';
for (const width of [1440, 1024]) {
  test(`prospective validation workspace ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(`${project}/validation?case=AXIS-PROSPECTIVE-ERAP1-EAST1-001`);
    await expect(page.getByRole('heading', { name: 'Scientific Decision Validation', level: 1 })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Prospective case — EAST-1 / GRWD0715' })).toBeVisible();
    for (const name of ['Frozen', 'Current position', 'Unknown', 'Future evidence that matters', 'Outcome scenarios', 'Reveals']) {
      await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
    }
    await expect(page.locator('main, #main').first()).toContainText('independent scientific review pending');
    await expect(page.locator('main, #main').first()).toContainText('None yet');
    await expect(page.locator('main, #main').first()).toContainText('Not a commercialization blocker');
    await page.getByText('D1 — Quantitative', { exact: false }).click();
    await expect(page.getByText('Unvalidated assay, interference', { exact: false })).toBeVisible();
    await page.screenshot({ path: `test-results/prospective-${width}.png`, fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    expect(errors).toEqual([]);
  });
  test(`retrospective validation workspace ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const shot = async name => page.screenshot({ path: `test-results/validation-${width}-${name}.png`, fullPage: true });
    await page.goto(`${project}/validation?case=erap1-axspa-t2016`);
    await expect(page.getByRole('heading', { name: 'Scientific Decision Validation', level: 1 })).toBeVisible();
    await expect(page.locator('.proposal-banner').first()).toContainText('DEVELOPMENT benchmark');
    await expect(page.getByRole('heading', { name: 'Evidence timeline' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Decision at T' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Validation matrix' })).toBeVisible();
    await expect(page.locator('main, #main').first()).toContainText('there is no AXIS score');
    await shot('1-real-case');
    await page.goto(`${project}/validation?case=erap1-axspa-t2011`);
    await expect(page.locator('main, #main').first()).toContainText('Not revealed');
    await expect(page.locator('main, #main').first()).not.toContainText('PMID:31841350');
    await shot('2-sealed-case');
    await page.goto(`${project}/validation?case=syn-generic-positive`);
    await expect(page.locator('.proposal-banner.synthetic').first()).toContainText('SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE');
    await expect(page.locator('main, #main').first()).toContainText('supported by future evidence');
    await expect(page.locator('main, #main').first()).toContainText('Dr Example');
    await shot('3-synthetic-reviewed');
    expect(errors).toEqual([]);
  });
}
