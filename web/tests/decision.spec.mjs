import { test, expect } from '@playwright/test';

const project='/projects/AXIS-DD-ERAP1-CURATED-001';
for(const width of [1440,1024]) {
  test(`experimental decision workspace ${width}`,async({page})=>{
    await page.setViewportSize({width,height:1000});
    const errors=[];const remote=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:'))remote.push(r.url());});
    const shot=async(name)=>page.screenshot({path:`test-results/decision-${width}-${name}.png`});
    const focusOn=async(name,level=2)=>{const h=page.getByRole('heading',{name,exact:true,level});await h.scrollIntoViewIfNeeded();return h;};

    await page.goto(`${project}/cellular`);
    await page.getByRole('link',{name:'Decision',exact:true}).first().click();
    await expect(page).toHaveURL(/\/decision$/);
    await expect(page.getByRole('heading',{name:'Decision',exact:true,level:1})).toBeVisible();
    await expect(page.locator('.proposal-banner')).toContainText('not scientific truth');
    await expect(page.getByRole('heading',{name:'Current scientific position'})).toBeVisible();
    await shot('1-overview');

    await focusOn('Critical uncertainty');
    const critical=page.locator('.critical-uncertainty');
    await expect(critical).toContainText('Why this is critical');
    await expect(critical).toContainText('selectivity is unresolved, so an off-target explanation remains viable');
    await expect(critical).toContainText('Other open uncertainties and why they were not selected');
    await expect(critical).toContainText('no numerical score');
    await shot('2-critical-uncertainty');

    await focusOn('Competing explanations');
    await expect(page.getByRole('heading',{name:'On-target ERAP1 modulation'})).toBeVisible();
    await expect(page.locator('.strategy-grid .card').first()).toContainText('ai suggestion');
    await shot('3-competing-explanations');
    const inspect=page.locator('[data-decision-explanation]').first();
    await inspect.focus();await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog')).toContainText('EXPLANATION EVIDENCE');
    await expect(page.getByRole('dialog')).toContainText('absence of evidence is listed as unresolved');
    await shot('4-explanation-evidence');
    await page.keyboard.press('Escape');
    await expect(inspect).toBeFocused();

    await focusOn('Experiment comparison');
    await expect(page.locator('table caption')).toContainText('Candidate experiments considered');
    await expect(page.getByText('Low discrimination').first()).toBeVisible();
    await expect(page.locator('table')).toContainText('not provided');
    await shot('5-experiment-comparison');

    await focusOn('Recommended discriminating experiment');
    await expect(page.locator('main, #main').first()).toContainText('AXIS suggestion — not performed');
    await shot('6-recommended-experiment');
    await focusOn('Why this experiment?',3);
    await expect(page.locator('section[aria-labelledby="why-experiment"]')).toContainText('Explanations it separates');
    await shot('7-why-this-experiment');
    await focusOn('Outcome tree',3);
    const tree=page.locator('.outcome-tree');
    await expect(tree).toContainText('Next action');
    await expect(tree).toContainText('non interpretable');
    await expect(page.getByText('No probabilities are assigned to branches')).toBeVisible();
    await shot('8-outcome-tree');

    await focusOn('What would change our mind?');
    await expect(page.locator('#mind ~ p').first()).toContainText('prospective / hypothetical');
    await focusOn('Investigator constraints');
    await expect(page.locator('#constraints ~ div').first()).toContainText('Feasibility not assessed against local resource constraints');
    await shot('12-unknown-constraints');

    await focusOn('Evidence and rule trace');
    for(const summary of await page.locator('#trace ~ details summary').all())await summary.click();
    await expect(page.locator('#trace ~ details').first()).toContainText('DECISION-CRIT-001');
    await shot('9-decision-trace');
    await focusOn('Decision history');
    await expect(page.locator('#history ~ article').first()).toContainText('First decision state');
    await shot('10-history-diff');

    await page.locator('[data-decision-experiment]').filter({hasText:'Repeat the reported'}).first().scrollIntoViewIfNeeded();
    await page.locator('[data-decision-experiment]').filter({hasText:'Repeat the reported'}).first().click();
    await expect(page.getByRole('dialog')).toContainText('Low discrimination');
    await expect(page.getByRole('dialog')).toContainText('Outcome scenarios (prospective)');
    await shot('11-non-discriminating-experiment');
    await page.keyboard.press('Escape');

    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    expect(errors).toEqual([]);
    expect(remote).toEqual([]);
  });
}
test('decision section links are keyboard operable',async({page})=>{
  await page.goto(`${project}/decision`);
  const link=page.getByRole('navigation',{name:'Decision sections'}).getByRole('link',{name:'Comparison'});
  await link.focus();await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#comparison$/);
});
