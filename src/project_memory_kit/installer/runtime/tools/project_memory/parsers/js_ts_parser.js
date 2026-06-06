#!/usr/bin/env node
"use strict";

let ts;
try {
  ts = require("typescript");
} catch (error) {
  process.stdout.write(JSON.stringify({ ok: false, reason: "typescript unavailable" }));
  process.exit(0);
}

const fs = require("fs");
const path = require("path");

const [, , rootArg, fileArg, moduleName] = process.argv;
const sourceText = fs.readFileSync(fileArg, "utf8");
const scriptKind = scriptKindForPath(fileArg);
const sourceFile = ts.createSourceFile(fileArg, sourceText, ts.ScriptTarget.Latest, true, scriptKind);
const symbols = [];
const imports = [];

function scriptKindForPath(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".tsx") return ts.ScriptKind.TSX;
  if (ext === ".ts" || ext === ".mts" || ext === ".cts") return ts.ScriptKind.TS;
  if (ext === ".jsx") return ts.ScriptKind.JSX;
  return ts.ScriptKind.JS;
}

function locFromPos(pos) {
  return sourceFile.getLineAndCharacterOfPosition(pos).line + 1;
}

function startLine(node) {
  return locFromPos(node.getStart(sourceFile, false));
}

function endLine(node) {
  return locFromPos(node.getEnd());
}

function signature(node) {
  return sourceText.slice(node.getStart(sourceFile, false), Math.min(node.getEnd(), sourceText.length)).split(/\r?\n/, 1)[0].trim().slice(0, 300);
}

function hasModifier(node, kind) {
  return Boolean(node.modifiers && node.modifiers.some((modifier) => modifier.kind === kind));
}

function nameText(node, fallback) {
  if (!node || !node.name) return fallback;
  return node.name.getText(sourceFile);
}

function addImport(module, name, alias, line) {
  imports.push({ module, name: name || null, alias: alias || null, line });
}

function moduleText(moduleSpecifier) {
  if (!moduleSpecifier) return null;
  if (ts.isStringLiteral(moduleSpecifier) || ts.isNoSubstitutionTemplateLiteral(moduleSpecifier)) {
    return moduleSpecifier.text;
  }
  return null;
}

function collectImportDeclaration(node) {
  const module = moduleText(node.moduleSpecifier);
  if (!module) return;
  const line = startLine(node);
  const clause = node.importClause;
  if (!clause) {
    addImport(module, null, null, line);
    return;
  }
  if (clause.name) {
    addImport(module, "default", clause.name.text, line);
  }
  const bindings = clause.namedBindings;
  if (!bindings) return;
  if (ts.isNamespaceImport(bindings)) {
    addImport(module, "*", bindings.name.text, line);
    return;
  }
  for (const specifier of bindings.elements) {
    addImport(
      module,
      specifier.propertyName ? specifier.propertyName.text : specifier.name.text,
      specifier.propertyName ? specifier.name.text : null,
      line
    );
  }
}

function collectExportDeclaration(node) {
  const module = moduleText(node.moduleSpecifier);
  if (!module) return;
  const line = startLine(node);
  if (!node.exportClause) {
    addImport(module, "*", null, line);
    return;
  }
  if (ts.isNamespaceExport(node.exportClause)) {
    addImport(module, "*", node.exportClause.name.text, line);
    return;
  }
  for (const specifier of node.exportClause.elements) {
    addImport(
      module,
      specifier.propertyName ? specifier.propertyName.text : specifier.name.text,
      specifier.propertyName ? specifier.name.text : null,
      line
    );
  }
}

function collectRequireLike(node) {
  if (!ts.isCallExpression(node)) return;
  const expressionText = node.expression.getText(sourceFile);
  if (expressionText !== "require" && expressionText !== "import") return;
  const firstArg = node.arguments[0];
  const module = moduleText(firstArg);
  if (module) addImport(module, null, null, startLine(node));
}

function collectUsage(node) {
  const calls = new Set();
  const refs = new Set();
  const excluded = new Set(["if", "for", "while", "switch", "catch", "function", "return", "typeof", "new", "class", "super"]);

  function visit(child) {
    if (ts.isCallExpression(child)) {
      const text = child.expression.getText(sourceFile);
      const first = text.split(".", 1)[0];
      if (!excluded.has(first)) calls.add(text);
    }
    if (ts.isJsxOpeningElement(child) || ts.isJsxSelfClosingElement(child) || ts.isJsxClosingElement(child)) {
      const tag = child.tagName.getText(sourceFile);
      if (/^[A-Z]/.test(tag)) {
        calls.add(tag);
        refs.add(tag);
      }
    }
    if (ts.isIdentifier(child)) {
      const text = child.text;
      if (!excluded.has(text)) refs.add(text);
    }
    ts.forEachChild(child, visit);
  }

  if (node.body) visit(node.body);
  return {
    calls: Array.from(calls).sort(),
    references: Array.from(refs).sort(),
  };
}

function addSymbol(kind, name, fqn, node, options = {}) {
  const usage = options.usage || collectUsage(node);
  symbols.push({
    name,
    fqn,
    kind,
    start_line: startLine(node),
    end_line: endLine(node),
    signature: signature(node),
    docstring: null,
    decorators: [],
    bases: options.bases || [],
    calls: usage.calls || [],
    references: usage.references || [],
  });
}

function classBases(node) {
  const bases = [];
  if (!node.heritageClauses) return bases;
  for (const clause of node.heritageClauses) {
    if (clause.token !== ts.SyntaxKind.ExtendsKeyword) continue;
    for (const item of clause.types) {
      bases.push(item.expression.getText(sourceFile));
    }
  }
  return bases;
}

function collectClass(node) {
  const name = nameText(node, "default");
  const classFqn = `${moduleName}.${name}`;
  addSymbol("class", name, classFqn, node, { usage: { calls: [], references: [] }, bases: classBases(node) });
  for (const member of node.members || []) {
    if (
      ts.isMethodDeclaration(member) ||
      ts.isConstructorDeclaration(member) ||
      ts.isGetAccessorDeclaration(member) ||
      ts.isSetAccessorDeclaration(member)
    ) {
      const methodName = ts.isConstructorDeclaration(member) ? "constructor" : nameText(member, "method");
      addSymbol("method", methodName, `${classFqn}.${methodName}`, member);
      continue;
    }
    if (ts.isPropertyDeclaration(member) && member.initializer) {
      if (ts.isArrowFunction(member.initializer) || ts.isFunctionExpression(member.initializer)) {
        const methodName = nameText(member, "method");
        addSymbol("method", methodName, `${classFqn}.${methodName}`, member);
      }
    }
  }
}

function collectFunction(node) {
  const name = nameText(node, hasModifier(node, ts.SyntaxKind.DefaultKeyword) ? "default" : "anonymous");
  if (name === "anonymous") return;
  const kind = hasModifier(node, ts.SyntaxKind.AsyncKeyword) ? "async_function" : "function";
  addSymbol(kind, name, `${moduleName}.${name}`, node);
}

function collectVariableStatement(node) {
  for (const declaration of node.declarationList.declarations) {
    if (!ts.isIdentifier(declaration.name) || !declaration.initializer) continue;
    const name = declaration.name.text;
    const init = declaration.initializer;
    if (ts.isArrowFunction(init) || ts.isFunctionExpression(init)) {
      addSymbol("function", name, `${moduleName}.${name}`, declaration);
    } else if (ts.isClassExpression(init)) {
      addSymbol("class", name, `${moduleName}.${name}`, declaration, { bases: classBases(init), usage: { calls: [], references: [] } });
    }
  }
}

function collectImportsDeep(node) {
  if (ts.isImportDeclaration(node)) collectImportDeclaration(node);
  if (ts.isExportDeclaration(node)) collectExportDeclaration(node);
  collectRequireLike(node);
  ts.forEachChild(node, collectImportsDeep);
}

function collectTopLevel(node) {
  if (ts.isFunctionDeclaration(node)) collectFunction(node);
  if (ts.isClassDeclaration(node)) collectClass(node);
  if (ts.isVariableStatement(node)) collectVariableStatement(node);
}

collectImportsDeep(sourceFile);
for (const statement of sourceFile.statements) {
  collectTopLevel(statement);
}

process.stdout.write(JSON.stringify({ ok: true, root: rootArg, symbols, imports, warnings: [] }));
