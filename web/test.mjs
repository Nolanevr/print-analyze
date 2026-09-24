// End-to-end test of dist/as-built-linker.html in headless Chromium.
// Needs Chromium (PLAYWRIGHT_BROWSERS_PATH or CHROMIUM_PATH) and python3 with PyMuPDF.
import { chromium } from "playwright-core";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const html = pathToFileURL(join(here, "..", "dist", "as-built-linker.html")).href;
const work = mkdtempSync(join(tmpdir(), "abl-"));

function chromiumPath() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  const root = process.env.PLAYWRIGHT_BROWSERS_PATH || "/opt/pw-browsers";
  for (const d of readdirSync(root).filter((d) => d.startsWith("chromium")).sort().reverse()) {
    for (const p of ["chrome-linux/chrome", "chrome-linux64/chrome"]) if (existsSync(join(root, d, p))) return join(root, d, p);
  }
  return undefined;
}
const py = (script, ...args) => execFileSync("python3", ["-c", script, ...args], { encoding: "utf8" });
let failures = 0;
const check = (ok, what) => { console.log(`${ok ? "PASS" : "FAIL"}  ${what}`); if (!ok) failures++; };

const browser = await chromium.launch({ executablePath: chromiumPath() });

async function newPage() {
  const page = await browser.newPage({ acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(html);
  return { page, errors };
}
async function build(page, name) {
  const [dl] = await Promise.all([page.waitForEvent("download"), page.click("#buildBtn")]);
  const out = join(work, name);
  await dl.saveAs(out);
  return out;
}

// 1. Sample flow
{
  const { page, errors } = await newPage();
  await page.click("details summary");
  await page.click("#sampleBtn");
  await page.waitForFunction(() => document.querySelector("#sampleBtn").textContent === "Sample loaded");
  const counts = await page.evaluate(() => {
    const S = window.__abl.S;
    return { stds: [...S.standards.values()].map((s) => [s.label, s.pages.length]), on: S.callouts.filter((c) => c.on).map((c) => c.tok.text + "@" + (c.sheet + 1)), off: S.callouts.filter((c) => !c.on).map((c) => c.tok.text) };
  });
  check(JSON.stringify(counts.stds) === JSON.stringify([["1", 1], ["2", 1], ["5", 1], ["12", 2], ["14", 1], ["21", 1], ["30", 1]]), "book indexed from title block, continuation page joined to 12: " + JSON.stringify(counts.stds));
  check(counts.on.length === 10, "10 bubble numbers linked: " + counts.on.join(" "));
  check(counts.off.length >= 2 && counts.off.includes("30") && counts.off.includes("5"), "note text '30' and '5' skipped by size filter: " + counts.off.join(" "));
  const out = await build(page, "sample.pdf");
  const res = py(`
import sys, pymupdf, json
d = pymupdf.open(sys.argv[1])
r = {"pages": d.page_count, "toc": [t[1] for t in d.get_toc()]}
r["links0"] = [(l["page"], d[l["page"]].get_text().split("STRUCTURE NO.")[-1].split()[0] if "STRUCTURE NO." in d[l["page"]].get_text() else "") for l in d[0].get_links()]
r["index_text"] = d[2].get_text()[:80]
r["back"] = sorted({l["page"] for l in d[6].get_links()})
print(json.dumps(r))`, out);
  const r = JSON.parse(res);
  check(r.pages === 2 + 1 + 8, "2 sheets + index + 8 standard pages: " + r.pages);
  check(r.links0.length === 6 && r.links0.every(([, n]) => n), "sheet 1 links land on standard pages: " + JSON.stringify(r.links0));
  check(r.index_text.includes("Structures Used"), "index page present");
  check(r.toc.includes("Structure 12") && r.toc.includes("Sheet 2"), "bookmarks: " + r.toc.join(" | "));
  check(r.back.length >= 2, "standard page links back to sheets/index: " + JSON.stringify(r.back));
  check(errors.length === 0, "no page errors " + errors.join("; "));
  await page.close();
}

// 2. Rotated print + rotated standards page, numbers typed next to poles
{
  const bookPath = join(work, "book.pdf"), printPath = join(work, "print.pdf");
  const pos = JSON.parse(py(`
import sys, pymupdf, json
b = pymupdf.open()
for num in ["101", "102", "103"]:
    p = b.new_page(width=792, height=612)
    p.insert_text((650, 580), "DWG", fontsize=8)
    p.insert_text((690, 580), num, fontsize=14)
b[1].set_rotation(90)
b.save(sys.argv[1])
d = pymupdf.open()
p = d.new_page(width=1224, height=792)
for i, t in enumerate(["101", "102", "103", "102"]):
    p.insert_text((100 + i * 200, 300), t, fontsize=10)
    p.insert_text((100 + i * 200, 330), "300'", fontsize=10)
p.insert_text((100, 360), "101", fontsize=6)
p.set_rotation(90)
d.save(sys.argv[2])
# user-space centre of the first "101" on the print and of the book number
print(json.dumps({"print": [110, 792 - 296], "book": [698, 612 - 575]}))`, bookPath, printPath));
  const { page, errors } = await newPage();
  await page.setInputFiles("#bookInput", bookPath);
  await page.waitForFunction(() => window.__abl.S.bookPages.length === 3);
  await page.evaluate(([x, y]) => { window.__abl.teachBook(x, y); window.__abl.render(); }, pos.book);
  const nums = await page.evaluate(() => window.__abl.S.bookPages.map((p) => p.auto));
  check(JSON.stringify(nums) === '["101","102","103"]', "numbers read on every book page incl. rotated: " + nums);
  await page.setInputFiles("#printInput", printPath);
  await page.waitForFunction(() => window.__abl.S.print);
  await page.evaluate(([x, y]) => { window.__abl.teachPrint(x, y); window.__abl.render(); }, pos.print);
  const on = await page.evaluate(() => window.__abl.S.callouts.filter((c) => c.on).length);
  check(on === 4, "4 callouts linked, small '101' skipped: " + on);
  const out = await build(page, "rotated.pdf");
  const r = JSON.parse(py(`
import sys, pymupdf, json
d = pymupdf.open(sys.argv[1])
p = d[0]
ok = []
for l in p.get_links():
    shown = l["from"] * p.derotation_matrix   # back to unrotated page space
    ok.append(p.get_textbox(shown + (-1, -1, 1, 1)).strip())
rot = d[3]  # index at 1, standards 101,102(rotated),103 at 2..4
banner = [s["text"] for b in rot.get_text("dict")["blocks"] for ln in b.get("lines", []) for s in ln["spans"]]
bb = [s for b in rot.get_text("dict")["blocks"] for ln in b.get("lines", []) for s in ln["spans"] if s["text"].startswith("Structure")]
shown = pymupdf.Rect(bb[0]["bbox"]) * rot.rotation_matrix if bb else None
print(json.dumps({"texts": ok, "rot": rot.rotation, "banner_pos": list(shown) if shown else None}))`, out));
  check(r.texts.every((t) => ["101", "102", "103"].includes(t)) && r.texts.length === 4, "links on rotated sheet cover the numbers: " + JSON.stringify(r.texts));
  check(r.rot === 90 && r.banner_pos && r.banner_pos[0] < 40 && r.banner_pos[1] < 40, "banner at visual top-left of rotated standard: " + JSON.stringify(r.banner_pos));
  check(errors.length === 0, "no page errors " + errors.join("; "));
  await page.close();
}

await browser.close();
console.log(failures ? `${failures} check(s) failed` : "all checks passed");
process.exit(failures ? 1 : 0);
