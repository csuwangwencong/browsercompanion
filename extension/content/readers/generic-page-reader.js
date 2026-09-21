(function () {
  const MAX_BLOCKS = 300;

  function read(action) {
    const name = action?.name;
    const params = action?.params || {};
    const documentModel = buildDocumentModel();

    if (name === "page_meta") return pageMeta(documentModel);
    if (name === "selection") return selection();
    if (name === "outline") return { outline: documentModel.outline, url: documentModel.url, title: documentModel.title };
    if (name === "content") return content(documentModel, params);
    if (name === "search") return search(documentModel, params);

    throw new Error(`Unsupported read action: ${name}`);
  }

  function pageMeta(model) {
    return {
      title: model.title,
      url: model.url,
      language: model.language,
      pageType: model.pageType,
      description: metaContent("description"),
    };
  }

  function selection() {
    const selected = String(window.getSelection()?.toString() || "").trim();
    return {
      available: selected.length > 0,
      text: limitText(selected, 4000),
      before: "",
      after: "",
    };
  }

  function content(model, params) {
    const chunkSize = clampInt(params.chunkSize || params.chunk_size || 8000, 1000, 16000);
    const cursor = clampInt(params.cursor || 0, 0, Math.max(0, model.blocks.length - 1));
    const selectedBlocks = [];
    let length = 0;

    for (let index = cursor; index < model.blocks.length; index += 1) {
      const block = model.blocks[index];
      const blockLength = block.text.length + 1;
      if (selectedBlocks.length && length + blockLength > chunkSize) break;
      selectedBlocks.push(block);
      length += blockLength;
    }

    const nextCursor = cursor + selectedBlocks.length;
    return {
      snapshotId: model.snapshotId,
      title: model.title,
      url: model.url,
      outline: model.outline,
      blocks: selectedBlocks,
      text: selectedBlocks.map((block) => block.text).join("\n"),
      nextCursor: nextCursor < model.blocks.length ? String(nextCursor) : null,
      hasMore: nextCursor < model.blocks.length,
    };
  }

  function search(model, params) {
    const query = String(params.query || "").trim().toLowerCase();
    if (!query) return { matches: [] };

    const matches = model.blocks
      .filter((block) => block.text.toLowerCase().includes(query))
      .slice(0, 20)
      .map((block) => ({
        blockId: block.id,
        type: block.type,
        headingPath: block.headingPath,
        text: limitText(block.text, 800),
      }));

    return { query, matches, count: matches.length };
  }

  function buildDocumentModel() {
    const root = document.querySelector("article") || document.querySelector("main") || document.querySelector('[role="main"]') || document.body;
    const blocks = [];
    const outline = [];
    const headingStack = [];
    const nodes = root.querySelectorAll("h1,h2,h3,h4,h5,h6,p,li,blockquote,pre,code,table,img,a");

    for (const node of nodes) {
      if (blocks.length >= MAX_BLOCKS) break;
      if (!isVisible(node) || isInsideIgnored(node)) continue;

      const tag = node.tagName.toLowerCase();
      const text = extractText(node, tag);
      if (!text || text.length < 2) continue;

      const block = {
        id: `b${blocks.length + 1}`,
        type: blockType(tag),
        text: limitText(text, 2000),
        headingPath: [...headingStack],
      };

      if (/^h[1-6]$/.test(tag)) {
        const level = Number(tag.slice(1));
        block.level = level;
        while (headingStack.length >= level) headingStack.pop();
        headingStack.push(text);
        block.headingPath = [...headingStack];
        outline.push({ id: block.id, level, text: block.text });
      }

      blocks.push(block);
    }

    return {
      snapshotId: `snap-${Date.now()}`,
      title: document.title || "",
      url: location.href,
      language: document.documentElement.lang || "",
      pageType: root.tagName?.toLowerCase() === "article" ? "article" : "page",
      outline,
      blocks,
    };
  }

  function extractText(node, tag) {
    if (tag === "img") return node.getAttribute("alt") || "";
    if (tag === "table") return Array.from(node.querySelectorAll("tr")).map((row) => row.innerText.trim()).filter(Boolean).join("\n");
    return node.innerText?.trim() || node.textContent?.trim() || "";
  }

  function blockType(tag) {
    if (/^h[1-6]$/.test(tag)) return "heading";
    if (tag === "li") return "list_item";
    if (tag === "blockquote") return "quote";
    if (tag === "pre" || tag === "code") return "code";
    if (tag === "table") return "table";
    if (tag === "img") return "image_alt";
    if (tag === "a") return "link";
    return "paragraph";
  }

  function isInsideIgnored(node) {
    return Boolean(node.closest("script,style,noscript,nav,footer,header,aside,[aria-hidden='true']"));
  }

  function isVisible(node) {
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width >= 0 && rect.height >= 0;
  }

  function metaContent(name) {
    return document.querySelector(`meta[name="${name}"]`)?.getAttribute("content") || "";
  }

  function clampInt(value, min, max) {
    const number = Number.parseInt(value, 10);
    if (!Number.isFinite(number)) return min;
    return Math.max(min, Math.min(max, number));
  }

  function limitText(text, maxLength) {
    return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
  }

  window.BrowserCompanionPageReader = { read };
})();
