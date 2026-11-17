import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { extname, join, relative, resolve } from "node:path";
import test from "node:test";
import { createGameKnifeI18n, normalizeLanguage, namespaces, resources } from "../dist/index.js";

test("normalizes browser language variants to a supported language", () => {
  assert.equal(normalizeLanguage("zh-CN"), "zh-CN");
  assert.equal(normalizeLanguage("zh-TW"), "zh-CN");
  assert.equal(normalizeLanguage("en-US"), "en");
  assert.equal(normalizeLanguage("fr-FR"), "en");
  assert.equal(normalizeLanguage(undefined), "en");
});

test("defaults to English when no language preference is stored", async () => {
  const instance = await createGameKnifeI18n({ detectLanguage: false });

  assert.equal(instance.resolvedLanguage, "en");
  assert.equal(instance.t("navigation.home", { ns: "common" }), "Home");
});

test("keeps English and Simplified Chinese resource keys aligned", () => {
  for (const namespace of namespaces) {
    assert.deepEqual(readLeafKeys(resources.en[namespace]), readLeafKeys(resources["zh-CN"][namespace]), namespace);
  }
});

test("uses UI splitting as the public tool name in both languages", () => {
  assert.equal(resources.en.tools.items["asset-board"], "UI Splitting");
  assert.equal(resources["zh-CN"].tools.items["asset-board"], "UI拆分");
});

test("switches translations and synchronizes the document language", async () => {
  const previousDocument = globalThis.document;
  globalThis.document = { documentElement: { lang: "", dir: "" } };

  try {
    const instance = await createGameKnifeI18n({ initialLanguage: "zh-CN", detectLanguage: false });

    assert.equal(instance.t("navigation.home", { ns: "common" }), "首页");
    assert.equal(instance.t("language.switchToEnglish", { ns: "common" }), "切换到英语");
    assert.equal(globalThis.document.documentElement.lang, "zh-CN");
    assert.equal(globalThis.document.documentElement.dir, "ltr");

    await instance.changeLanguage("en");
    assert.equal(instance.t("navigation.home", { ns: "common" }), "Home");
    assert.equal(instance.t("language.switchToSimplifiedChinese", { ns: "common" }), "Switch to Simplified Chinese");
    assert.equal(globalThis.document.documentElement.lang, "en");
    assert.equal(globalThis.document.documentElement.dir, "ltr");
  } finally {
    if (previousDocument === undefined) {
      delete globalThis.document;
    } else {
      globalThis.document = previousDocument;
    }
  }
});

test("localizes job filters added by the workflow foundations in both languages", async () => {
  const instance = await createGameKnifeI18n({ initialLanguage: "en", detectLanguage: false });
  const english = instance.getFixedT("en", "jobs");
  const chinese = instance.getFixedT("zh-CN", "jobs");

  assert.equal(english("categories.quality.label"), "Quality checks");
  assert.equal(chinese("categories.quality.label"), "质量检查");
  assert.equal(english("categories.export.label"), "Project exports");
  assert.equal(chinese("categories.export.label"), "项目导出");
  assert.equal(english("resultCount", { count: 1 }), "1 job");
  assert.equal(english("resultCount", { count: 2 }), "2 jobs");
  assert.equal(chinese("resultCount", { count: 2 }), "共 2 个任务");
});

test("keeps repository source and developer content in English", () => {
  const repositoryRoot = resolve(process.cwd(), "../..");
  const sourceRoots = [
    "apps",
    "docker",
    "docs",
    "packages",
    "scripts",
    "services",
    "services-extra",
  ];
  const violations = sourceRoots.flatMap((sourceRoot) =>
    walkSourceFiles(join(repositoryRoot, sourceRoot))
      .filter((filePath) => {
        const repositoryPath = relative(repositoryRoot, filePath);
        return !filePath.includes(`${join("locales", "zh-CN")}`) && repositoryPath !== join("packages", "i18n", "test", "i18n.test.mjs");
      })
      .flatMap((filePath) => {
        const lines = readFileSync(filePath, "utf8").split(/\r?\n/);
        return lines.flatMap((line, index) => (/\p{Script=Han}/u.test(line) ? [`${relative(repositoryRoot, filePath)}:${index + 1}`] : []));
      }),
  );

  assert.deepEqual(violations, []);
});

function readLeafKeys(value, prefix = "") {
  return Object.entries(value)
    .flatMap(([key, child]) => {
      const path = prefix ? `${prefix}.${key}` : key;
      return child && typeof child === "object" ? readLeafKeys(child, path) : [path];
    })
    .sort();
}

function walkSourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const filePath = join(directory, entry.name);
    if (entry.isDirectory()) {
      return ["__pycache__", "dist", "node_modules"].includes(entry.name) ? [] : walkSourceFiles(filePath);
    }
    return [".css", ".Dockerfile", ".html", ".js", ".json", ".md", ".mjs", ".py", ".sh", ".ts", ".tsx", ".yaml", ".yml"].includes(
      extname(entry.name),
    )
      ? [filePath]
      : [];
  });
}
