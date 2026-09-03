(() => {
  const editableEntityHighlightRanges = new Map();
  const entityClipboardType = "application/x-cxms-entity-links+json";
  const sheetClipboardToken = crypto.randomUUID();
  const recentEntityKey = `sew-entity-recents:${window.location.pathname}`;

  const readRecentEntities = () => {
    try {
      return JSON.parse(sessionStorage.getItem(recentEntityKey) || "[]");
    } catch (_error) {
      return [];
    }
  };

  const rememberRecentEntity = (entity) => {
    const recents = readRecentEntities().filter((item) => item.id !== entity.id);
    recents.unshift(entity);
    try {
      sessionStorage.setItem(recentEntityKey, JSON.stringify(recents.slice(0, 6)));
    } catch (_error) {
      // Linking must continue even when browser storage is unavailable.
    }
  };

  const renderEditableEntityHighlights = () => {
    if (!window.CSS?.highlights || typeof window.Highlight !== "function") return;

    const ranges = [...editableEntityHighlightRanges.values()].flat();
    CSS.highlights.set("sew-entity-links", new Highlight(...ranges));
  };

  const initialiseReviewBlock = (block) => {
    if (block.dataset.reviewInitialised) return;

    block.dataset.reviewInitialised = "true";

    const editor = block.querySelector("[data-review-editor]");
    const input = block.querySelector("[data-review-input]");

    // Sub-headings do not have a publication editor. Leave them rendered and
    // continue initialising entity controls on the statistic blocks below.
    if (!editor || !input) return;

    const original = block.querySelector(
      ".sew-original .sew-rendered-content",
    );

    const normaliseText = (value) => value.replace(/\s+/g, " ").trim();

    // Do not collapse or trim whitespace here. Spaces, line breaks and
    // backspaces are editorial changes and must trigger re-review.
    const comparableMarkup = (value) =>
      value.replace(/\r\n?/g, "\n");

    const editorMarkup = () => {
      const clone = editor.cloneNode(true);

      clone.querySelectorAll("[data-entity-ref]").forEach((tag) => {
        tag.replaceWith(document.createTextNode(tag.textContent));
      });

      return clone.innerHTML;
    };

    const sessionStartMarkup = comparableMarkup(editorMarkup());

    const tokenise = (value) =>
      normaliseText(value).match(/\S+\s*/g) || [];

    const renderDiff = (before, after) => {
      const oldTokens = tokenise(before);
      const newTokens = tokenise(after);

      const rows = Array.from(
        { length: oldTokens.length + 1 },
        () => Array(newTokens.length + 1).fill(0),
      );

      for (
        let oldIndex = oldTokens.length - 1;
        oldIndex >= 0;
        oldIndex -= 1
      ) {
        for (
          let newIndex = newTokens.length - 1;
          newIndex >= 0;
          newIndex -= 1
        ) {
          rows[oldIndex][newIndex] =
            normaliseText(oldTokens[oldIndex]) ===
            normaliseText(newTokens[newIndex])
              ? rows[oldIndex + 1][newIndex + 1] + 1
              : Math.max(
                  rows[oldIndex + 1][newIndex],
                  rows[oldIndex][newIndex + 1],
                );
        }
      }

      const fragment = document.createDocumentFragment();
      let oldIndex = 0;
      let newIndex = 0;

      while (
        oldIndex < oldTokens.length ||
        newIndex < newTokens.length
      ) {
        if (
          oldIndex < oldTokens.length &&
          newIndex < newTokens.length &&
          normaliseText(oldTokens[oldIndex]) ===
            normaliseText(newTokens[newIndex])
        ) {
          fragment.append(document.createTextNode(newTokens[newIndex]));
          oldIndex += 1;
          newIndex += 1;
        } else if (
          newIndex < newTokens.length &&
          (
            oldIndex === oldTokens.length ||
            rows[oldIndex][newIndex + 1] >=
              rows[oldIndex + 1][newIndex]
          )
        ) {
          const added = document.createElement("ins");
          added.textContent = newTokens[newIndex];
          added.title = "Added wording";
          fragment.append(added);
          newIndex += 1;
        } else {
          const removed = document.createElement("del");
          removed.textContent = oldTokens[oldIndex];
          removed.title = "Removed wording";
          fragment.append(removed);
          oldIndex += 1;
        }
      }

      return fragment;
    };

    const updateChangedState = () => {
      if (!original) return;

      let badge = block.querySelector("[data-change-badge]");

      if (!badge) {
        badge = document.createElement("span");
        badge.className = "sew-change-badge";
        badge.dataset.changeBadge = "";
        badge.textContent = "Changed";

        const headerActions = block.querySelector(
          ".sew-card-header-actions",
        );

        if (headerActions) {
          headerActions.insertBefore(
            badge,
            headerActions.querySelector("[data-toggle-accepted]") ||
              headerActions.querySelector("[data-remove-review-block]"),
          );
        } else {
          block.querySelector("header")?.appendChild(badge);
        }
      }

      const currentMarkup = comparableMarkup(editorMarkup());
      const changedThisSession =
        sessionStartMarkup !== currentMarkup;
      const differsFromResearcher =
        comparableMarkup(original.innerHTML) !== currentMarkup;

      block.classList.toggle(
        "has-changes",
        changedThisSession,
      );

      badge.hidden = !changedThisSession;

      let diff = block.querySelector("[data-change-diff]");

      if (!diff) {
        diff = document.createElement("div");
        diff.className = "sew-change-diff";
        diff.dataset.changeDiff = "";
        diff.setAttribute("aria-live", "polite");

        original
          .closest(".sew-original")
          ?.appendChild(diff);
      }

      diff.hidden = !differsFromResearcher;
      diff.replaceChildren();

      if (!differsFromResearcher) return;

      const label = document.createElement("strong");
      label.textContent = "Exact wording changes: ";
      diff.appendChild(label);

      if (
        normaliseText(original.textContent) ===
        normaliseText(editor.textContent)
      ) {
        diff.append(
          document.createTextNode(
            "Whitespace or formatting changed; visible wording is otherwise unchanged.",
          ),
        );
      } else {
        diff.appendChild(
          renderDiff(original.textContent, editor.textContent),
        );
      }
    };

    const sync = () => {
      input.value = editorMarkup();
      updateChangedState();
    };

    editor.addEventListener("input", sync);

    editor.addEventListener("paste", (event) => {
      event.preventDefault();

      document.execCommand(
        "insertText",
        false,
        event.clipboardData.getData("text/plain"),
      );

      sync();
    });

    block
      .querySelectorAll("[data-review-format]")
      .forEach((button) => {
        button.addEventListener("mousedown", (event) => {
          event.preventDefault();
          editor.focus();

          document.execCommand(
            button.dataset.reviewFormat,
            false,
          );

          sync();
        });
      });

    updateChangedState();
  };

  document
    .querySelectorAll("[data-review-block]")
    .forEach(initialiseReviewBlock);

  const initialiseEntityControl = (control) => {
    if (control.dataset.entityInitialised) return;

    const results = control.querySelector("[data-entity-results]");
    const selected = control.querySelector(
      "[data-selected-entities]",
    );
    const suggestions = control.querySelector(
      "[data-entity-suggestions]",
    );

    const editor = control
      .closest("[data-review-block], [data-content-block]")
      ?.querySelector("[data-review-editor], [data-editor]");

    if (!editor || !results || !selected || !suggestions) return;

    control.dataset.entityInitialised = "true";

    editor
      .closest(".sew-working-editor")
      ?.appendChild(results);

    let timer;
    let controller;
    let highlightFrame;
    let nextOffset = 0;
    let activeIndex = -1;
    let queryContext = null;
    let savedMentionContext = null;
    let recognitionTimer;
    let recognitionController;
    let recognitionActiveIndex = -1;

    const highlightKey = crypto.randomUUID();

    const entityButtons = () => [
      ...results.querySelectorAll("[data-entity-result]"),
    ];

    const setActive = (index) => {
      const buttons = entityButtons();

      buttons.forEach((button) => {
        button.setAttribute("aria-selected", "false");
        button.tabIndex = -1;
      });

      if (!buttons.length) {
        activeIndex = -1;
        editor.removeAttribute("aria-activedescendant");
        return;
      }

      activeIndex = Math.max(
        0,
        Math.min(index, buttons.length - 1),
      );

      buttons[activeIndex].setAttribute(
        "aria-selected",
        "true",
      );

      buttons[activeIndex].tabIndex = 0;

      results.querySelector("[data-entity-lookup]")?.setAttribute(
        "aria-activedescendant",
        buttons[activeIndex].id,
      );
    };

    const announce = (message) => {
      if (suggestions) suggestions.textContent = message;
    };

    const closeResults = (message = "") => {
      clearTimeout(timer);
      controller?.abort();
      controller = null;
      queryContext = null;
      nextOffset = 0;
      activeIndex = -1;
      results.hidden = true;
      results.replaceChildren();
      editor.removeAttribute("aria-activedescendant");
      if (message) announce(message);
    };

    const contextStillMatches = (context) => {
      if (!context?.range) return false;
      try {
        return editor.contains(context.range.commonAncestorContainer) &&
          context.range.toString().trim() === context.text;
      } catch (_error) {
        return false;
      }
    };

    const sameRange = (left, right) => {
      if (!left || !right) return false;
      try {
        return left.compareBoundaryPoints(Range.START_TO_START, right) === 0 &&
          left.compareBoundaryPoints(Range.END_TO_END, right) === 0;
      } catch (_error) {
        return false;
      }
    };

    const unwrapMentionTags = (targetEditor) => {
      targetEditor
        .querySelectorAll("[data-entity-ref]")
        .forEach((tag) => {
          tag.replaceWith(
            document.createTextNode(tag.textContent),
          );
        });

      targetEditor.normalize();
    };

    const rangeInputs = (chip) => ({
      mention: chip.querySelector("input[name^='entity_mention_']"),
      start: chip.querySelector("input[name^='entity_start_']"),
      end: chip.querySelector("input[name^='entity_end_']"),
    });

    const textOffsetForPoint = (node, offset) => {
      const range = document.createRange();
      range.selectNodeContents(editor);
      range.setEnd(node, offset);
      return range.toString().length;
    };

    const rangeFromOffsets = (start, end) => {
      if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start) return null;
      const range = document.createRange();
      const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT);
      let position = 0;
      let startSet = false;
      let node;
      while ((node = walker.nextNode())) {
        const next = position + node.data.length;
        if (!startSet && start >= position && start <= next) {
          range.setStart(node, Math.min(start - position, node.data.length));
          startSet = true;
        }
        if (startSet && end >= position && end <= next) {
          range.setEnd(node, Math.min(end - position, node.data.length));
          return range;
        }
        position = next;
      }
      return null;
    };

    const ensureChipRange = (chip, allowStale = false) => {
      const inputs = rangeInputs(chip);
      const mention = inputs.mention?.value.trim() || "";
      let start = Number.parseInt(inputs.start?.value, 10);
      let end = Number.parseInt(inputs.end?.value, 10);
      if (!mention) return null;
      if (allowStale && Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end > start) {
        return { start, end, mention, inputs };
      }
      if (!Number.isInteger(start) || !Number.isInteger(end) || editor.innerText.slice(start, end) !== mention) {
        start = editor.innerText.indexOf(mention);
        end = start + mention.length;
      }
      if (start < 0 || editor.innerText.slice(start, end) !== mention) return null;
      if (inputs.start) inputs.start.value = String(start);
      if (inputs.end) inputs.end.value = String(end);
      return { start, end, mention, inputs };
    };

    const refreshMentionHighlights = () => {
      const ranges = [];

      const chips = [
        ...selected.querySelectorAll("[data-entity-id]"),
      ].sort((left, right) => {
        const leftWords =
          left
            .querySelector("label input")
            ?.value.trim() || "";

        const rightWords =
          right
            .querySelector("label input")
            ?.value.trim() || "";

        return rightWords.length - leftWords.length;
      });

      chips.forEach((chip) => {
        const annotation = ensureChipRange(chip);
        const range = annotation && rangeFromOffsets(annotation.start, annotation.end);
        if (range) ranges.push(range);
      });

      editableEntityHighlightRanges.set(
        highlightKey,
        ranges,
      );

      renderEditableEntityHighlights();
    };

    const scheduleMentionHighlights = () => {
      cancelAnimationFrame(highlightFrame);

      highlightFrame = requestAnimationFrame(() => {
        refreshMentionHighlights();
      });
    };

    const selectedOffsets = () => {
      const selection = window.getSelection();
      if (!selection?.rangeCount || !editor.contains(selection.anchorNode)) return null;
      const range = selection.getRangeAt(0);
      return {
        start: textOffsetForPoint(range.startContainer, range.startOffset),
        end: textOffsetForPoint(range.endContainer, range.endOffset),
        collapsed: range.collapsed,
      };
    };

    const annotationAtSelection = () => {
      const offsets = selectedOffsets();
      if (!offsets) return null;
      return [...selected.querySelectorAll("[data-entity-id]")].find((chip) => {
        const annotation = ensureChipRange(chip, true);
        if (!annotation) return false;
        return offsets.collapsed
          ? offsets.start >= annotation.start && offsets.start <= annotation.end
          : offsets.start < annotation.end && offsets.end > annotation.start;
      }) || null;
    };

    function updateToolbarState() {
      const toolbar = editor.closest(".sew-working-editor")?.querySelector(".sew-mini-toolbar");
      if (!toolbar) return;
      const states = {
        bold: document.queryCommandState("bold"),
        italic: document.queryCommandState("italic"),
      };
      Object.entries(states).forEach(([format, active]) => {
        const button = toolbar.querySelector(`[data-format="${format}"], [data-review-format="${format}"]`);
        button?.classList.toggle("is-active", active);
        button?.setAttribute("aria-pressed", String(active));
      });
      const linkButton = toolbar.querySelector("[data-link-entity]");
      const linked = Boolean(annotationAtSelection());
      linkButton?.classList.toggle("is-active", linked);
      linkButton?.setAttribute("aria-pressed", String(linked));
      if (linkButton) linkButton.title = linked ? "Unlink selected entity" : "Add entity link";
    }

    let previousEditorText = editor.innerText;

    const validateMentionTags = () => {
      const currentText = editor.innerText;
      let prefix = 0;
      while (prefix < previousEditorText.length && prefix < currentText.length && previousEditorText[prefix] === currentText[prefix]) prefix += 1;
      let suffix = 0;
      while (suffix < previousEditorText.length - prefix && suffix < currentText.length - prefix && previousEditorText[previousEditorText.length - 1 - suffix] === currentText[currentText.length - 1 - suffix]) suffix += 1;
      const oldEnd = previousEditorText.length - suffix;
      const newEnd = currentText.length - suffix;
      const inserted = currentText.slice(prefix, newEnd);
      const delta = currentText.length - previousEditorText.length;

      selected
        .querySelectorAll("[data-entity-id]")
        .forEach((chip) => {
          const annotation = ensureChipRange(chip, true);
          if (!annotation) {
            if (rangeInputs(chip).mention?.value) chip.remove();
            return;
          }

          let { start, end } = annotation;
          if (oldEnd <= start) {
            start += delta;
            end += delta;
          } else if (prefix < end && oldEnd > start) {
            end = Math.max(start, end + delta);
          } else if (prefix >= end && prefix <= end + 1) {
            const startsSponsor = inserted.includes("(");
            if (chip.dataset.extendingAnnotation === "true" || startsSponsor) {
              end = newEnd;
              chip.dataset.extendingAnnotation = inserted.includes(")") ? "false" : "true";
            }
          }

          const updatedMention = currentText.slice(start, end).trimEnd();
          if (!updatedMention) {
            chip.remove();
            return;
          }
          end = start + updatedMention.length;
          annotation.inputs.mention.value = updatedMention;
          annotation.inputs.start.value = String(start);
          annotation.inputs.end.value = String(end);

        });

      previousEditorText = currentText;
      scheduleMentionHighlights();
      updateToolbarState();
    };

    const selectedMentionContext = () => {
      const selection = window.getSelection();

      if (
        !selection?.rangeCount ||
        !editor.contains(selection.anchorNode)
      ) {
        return null;
      }

      const range = selection.getRangeAt(0);

      if (!range.collapsed) {
        const text = range.toString().trim();

        return text.length >= 2 && text.length <= 80
          ? {
              text,
              range: range.cloneRange(),
              replace: false,
              start: textOffsetForPoint(range.startContainer, range.startOffset),
              end: textOffsetForPoint(range.endContainer, range.endOffset),
            }
          : null;
      }
      return null;
    };

    const addEntity = (entity, mentionOverride = "", trustedPaste = false, replacementText = "") => {
      if (!trustedPaste && !contextStillMatches(queryContext)) {
        closeResults("The selected wording changed. Select it again before linking.");
        editor.focus({ preventScroll: true });
        return;
      }

      let existingChip = selected.querySelector(
        `[data-entity-id="${entity.id}"]`,
      );

      const existingMention = existingChip
        ?.querySelector("label input")
        ?.value.trim();

      if (
        existingChip &&
        existingMention &&
        !editor.innerText.includes(existingMention)
      ) {
        existingChip.remove();
        existingChip = null;
      }

      if (existingChip) {
        closeResults();
        editor.focus({ preventScroll: true });
        return;
      }

      const activeContext = queryContext;
      let mentionText = mentionOverride || activeContext?.text || entity.name;
      let annotationStart = trustedPaste ? entity.annotation_start : activeContext?.start;
      let annotationEnd = trustedPaste ? entity.annotation_end : activeContext?.end;

      if (activeContext?.replace) {
        const insertedWording = replacementText || entity.name;
        const replacement = document.createTextNode(insertedWording);
        activeContext.range.deleteContents();
        activeContext.range.insertNode(replacement);
        activeContext.range.setStart(replacement, 0);
        activeContext.range.setEnd(replacement, insertedWording.length);
        mentionText = insertedWording;
        annotationStart = textOffsetForPoint(replacement, 0);
        annotationEnd = annotationStart + insertedWording.length;
        const caret = document.createRange();
        caret.setStartAfter(replacement);
        caret.collapse(true);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(caret);
        editor.dispatchEvent(new Event("input", { bubbles: true }));
      } else if (!trustedPaste && activeContext?.range) {
        annotationStart = textOffsetForPoint(activeContext.range.startContainer, activeContext.range.startOffset);
        annotationEnd = textOffsetForPoint(activeContext.range.endContainer, activeContext.range.endOffset);
      }

      if (!Number.isInteger(annotationStart)) annotationStart = editor.innerText.indexOf(mentionText);
      if (!Number.isInteger(annotationEnd)) annotationEnd = annotationStart + mentionText.length;

      const chip = document.createElement("span");
      chip.className = "sew-entity-chip";
      chip.dataset.entityId = entity.id;
      chip.dataset.entityName = entity.name;
      chip.dataset.entityType = entity.type;
      chip.dataset.canonicalId =
        entity.canonical_id || "";
      chip.dataset.entityUrl =
        entity.canonical_url || "";

      chip.append(
        document.createTextNode(`${entity.name} `),
      );

      const entityType =
        document.createElement("small");

      entityType.textContent = entity.type;

      const remove =
        document.createElement("button");

      remove.type = "button";
      remove.dataset.removeEntity = "";
      remove.setAttribute(
        "aria-label",
        `Unlink ${entity.name}`,
      );
      remove.textContent = "Unlink";

      const input =
        document.createElement("input");

      input.type = "hidden";
      input.name = control.dataset.fieldName;
      input.value = entity.id;

      const mentionLabel =
        document.createElement("label");

      const mention =
        document.createElement("input");

      mention.type = "hidden";
      mention.name =
        `${control.dataset.mentionPrefix}${entity.id}`;
      mention.value = mentionText;

      mentionLabel.appendChild(mention);

      const start = document.createElement("input");
      start.type = "hidden";
      start.name = `${control.dataset.mentionPrefix.replace("entity_mention_", "entity_start_")}${entity.id}`;
      start.value = String(annotationStart);

      const end = document.createElement("input");
      end.type = "hidden";
      end.name = `${control.dataset.mentionPrefix.replace("entity_mention_", "entity_end_")}${entity.id}`;
      end.value = String(annotationEnd);

      mentionLabel.append(start, end);

      chip.append(
        entityType,
        mentionLabel,
        remove,
        input,
      );

      selected.appendChild(chip);

      rememberRecentEntity(entity);

      closeResults();
      scheduleMentionHighlights();

      editor.dispatchEvent(
        new Event("input", { bubbles: true }),
      );
    };

    const appendResult = (entity) => {
      const button =
        document.createElement("button");

      button.id =
        `entity-result-${crypto.randomUUID()}`;
      button.type = "button";
      button.dataset.entityResult = "";
      button.setAttribute("role", "option");
      button.setAttribute(
        "aria-selected",
        "false",
      );
      button.tabIndex = -1;

      const identity = [
        entity.country_code,
        entity.ski_sponsor,
      ]
        .filter(Boolean)
        .join(" / ");

      button.textContent =
        `${entity.name}` +
        `${identity ? ` (${identity})` : ""}` +
        `${entity.canonical_id ? ` · ${entity.canonical_id}` : ""}`;

      button.addEventListener("click", () => {
        addEntity(entity);
      });

      results
        .querySelector("[data-entity-options]")
        ?.appendChild(button);
    };

    const runSearch = async (
      append = false,
      searchText = "",
    ) => {
      const query = searchText.trim();
      const options = results.querySelector(
        "[data-entity-options]",
      );

      if (!options) return;

      if (query.length < 2) {
        options.innerHTML =
          '<span class="sew-entity-loading">Type at least two characters.</span>';
        return;
      }

      if (!append) {
        nextOffset = 0;
        options.replaceChildren();
        activeIndex = -1;
      } else {
        options
          .querySelector("[data-show-more]")
          ?.remove();

        options
          .querySelector("[data-no-more]")
          ?.remove();
      }

      const loading =
        document.createElement("span");

      loading.className = "sew-entity-loading";
      loading.textContent = append
        ? "Loading more…"
        : "Searching…";

      options.appendChild(loading);
      results.hidden = false;

      controller?.abort();
      controller = new AbortController();

      try {
        const response = await fetch(
          `/workspace/sports-editorial/entities/search?q=${encodeURIComponent(query)}&offset=${nextOffset}`,
          { signal: controller.signal },
        );

        if (!response.ok) {
          throw new Error(
            `Entity search failed with status ${response.status}`,
          );
        }

        const payload = await response.json();

        // Ignore a response from an outdated request.
        if (
          !append &&
          results
            .querySelector("[data-entity-lookup]")
            ?.value.trim() !== query
        ) {
          return;
        }

        loading.remove();

        if (
          !append &&
          !payload.results.length
        ) {
          options.innerHTML =
            '<span class="sew-entity-loading">No matches.</span>';
        }

        payload.results.forEach(appendResult);
        nextOffset = payload.next_offset;

        if (payload.has_more) {
          const more =
            document.createElement("button");

          more.type = "button";
          more.dataset.showMore = "";
          more.textContent = "Show more";

          more.addEventListener("click", () => {
            runSearch(true, query);
          });

          options.appendChild(more);
        } else if (
          append &&
          payload.results.length
        ) {
          const end =
            document.createElement("span");

          end.className = "sew-entity-loading";
          end.dataset.noMore = "";
          end.textContent = "No more results.";

          options.appendChild(end);
        }
      } catch (error) {
        if (error.name === "AbortError") return;

        options.innerHTML =
          '<span class="sew-entity-loading">Search is temporarily unavailable.</span>';
      }
    };

    const scheduleSearch = (searchText) => {
      clearTimeout(timer);

      timer = setTimeout(() => {
        runSearch(false, searchText);
      }, 250);
    };

    results.id =
      results.id ||
      `entity-results-${crypto.randomUUID()}`;

    unwrapMentionTags(editor);
    validateMentionTags();

    editor.addEventListener("input", () => {
      validateMentionTags();
      if (queryContext) {
        closeResults("The wording changed, so the previous lookup was cancelled.");
      }
      scheduleRecognisedEntitySuggestion();
    });

    const meaningfulSearchText = (selectedText) => selectedText
      .trim()
      .replace(/\s*\([^)]*\)\s*$/, "")
      .trim()
      .replace(/[’']s$/i, "")
      .replace(/^[“\"']+|[”\"'.,;:!?]+$/g, "")
      .trim();

    const athleteWordingVariants = (entity) => {
      const identity = [entity.country_code, entity.ski_sponsor]
        .filter(Boolean)
        .join("/");
      const variants = identity
        ? [
            `${entity.name} (${identity})`,
            `${entity.name}'s (${identity})`,
            entity.name,
          ]
        : [entity.name, `${entity.name}'s`];
      return [...new Set(variants)];
    };

    const openEntityLookup = (context) => {
      if (!context || !editor.isContentEditable) return;
      queryContext = context;
      activeIndex = -1;
      nextOffset = 0;

      const label = document.createElement("label");
      label.className = "sew-entity-lookup-label";
      label.textContent = "Find the entity";

      const selectionStatus = document.createElement("strong");
      selectionStatus.className = "sew-entity-selection-status";
      selectionStatus.textContent = `Selected wording: “${context.text}”`;

      const lookup = document.createElement("input");
      lookup.type = "search";
      lookup.dataset.entityLookup = "";
      lookup.placeholder = "Search athlete, country or competition";
      lookup.autocomplete = "off";
      lookup.setAttribute("role", "combobox");
      lookup.setAttribute("aria-expanded", "true");
      const initialQuery = meaningfulSearchText(context.text);
      lookup.value = initialQuery;

      const options = document.createElement("div");
      options.dataset.entityOptions = "";
      options.id = `${results.id}-options`;
      options.setAttribute("role", "listbox");
      options.innerHTML = '<span class="sew-entity-loading">Searching…</span>';
      lookup.setAttribute("aria-controls", options.id);

      const recent = document.createElement("div");
      recent.className = "sew-entity-recents";
      const recentEntities = readRecentEntities();
      if (recentEntities.length) {
        const recentLabel = document.createElement("span");
        recentLabel.className = "sew-entity-loading";
        recentLabel.textContent = "Recently linked in this editing session";
        recent.appendChild(recentLabel);
        recentEntities.forEach((entity) => {
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = entity.name;
          button.addEventListener("click", () => addEntity(entity));
          recent.appendChild(button);
        });
      }

      lookup.addEventListener("input", () => {
        scheduleSearch(lookup.value);
      });
      lookup.addEventListener("keydown", (event) => {
        const buttons = entityButtons();
        if (event.key === "ArrowDown" && buttons.length) {
          event.preventDefault();
          setActive(activeIndex + 1);
        } else if (event.key === "ArrowUp" && buttons.length) {
          event.preventDefault();
          setActive(activeIndex <= 0 ? buttons.length - 1 : activeIndex - 1);
        } else if (event.key === "Enter") {
          event.preventDefault();
          if (activeIndex >= 0 && buttons[activeIndex]) buttons[activeIndex].click();
        } else if (event.key === "Escape") {
          event.preventDefault();
          closeResults();
          editor.focus({ preventScroll: true });
        }
      });

      results.replaceChildren(selectionStatus, label, lookup, recent, options);
      results.hidden = false;
      lookup.focus({ preventScroll: true });
      if (initialQuery.length >= 2) runSearch(false, initialQuery);
    };

    const typedAthletePrefixContext = () => {
      const selection = window.getSelection();
      if (!selection?.rangeCount || !selection.isCollapsed || !editor.contains(selection.anchorNode)) return null;
      const beforeCaretRange = document.createRange();
      beforeCaretRange.selectNodeContents(editor);
      beforeCaretRange.setEnd(selection.anchorNode, selection.anchorOffset);
      const beforeCaret = beforeCaretRange.toString();
      const match = beforeCaret.match(/(?:^|[^\p{L}’'-])(\p{Lu}\p{Ll}[\p{L}’'-]{1,})$/u);
      if (!match) return null;
      const text = match[1];
      const end = beforeCaret.length;
      const start = end - text.length;
      const range = rangeFromOffsets(start, end);
      if (!range) return null;
      return {
        text,
        range,
        replace: true,
        start,
        end,
      };
    };

    const scheduleRecognisedEntitySuggestion = () => {
      clearTimeout(recognitionTimer);
      recognitionController?.abort();
      recognitionActiveIndex = -1;
      editor.removeAttribute("aria-activedescendant");
      if (!suggestions || !editor.isContentEditable) return;
      suggestions.replaceChildren();

      const context = typedAthletePrefixContext();
      if (!context || context.text.length < 3) return;

      const waiting = document.createElement("span");
      waiting.className = "sew-entity-loading";
      waiting.textContent = `Looking for athletes matching “${context.text}”…`;
      suggestions.replaceChildren(waiting);

      recognitionTimer = setTimeout(async () => {
        recognitionController = new AbortController();
        try {
          const label = document.createElement("span");
          label.className = "sew-entity-loading";
          label.textContent = `Athlete suggestions for “${context.text}”`;
          const options = document.createElement("div");
          options.className = "sew-inline-entity-options";
          options.setAttribute("role", "listbox");
          options.setAttribute("aria-label", `Athletes matching ${context.text}`);
          suggestions.replaceChildren(label, options);

          const seen = new Set();
          let offset = 0;
          let hasMore = true;
          while (hasMore) {
            const response = await fetch(
              `/workspace/sports-editorial/entities/search?q=${encodeURIComponent(context.text)}&type=athlete&offset=${offset}`,
              { signal: recognitionController.signal },
            );
            if (!response.ok || !contextStillMatches(context)) return;
            const payload = await response.json();
            payload.results
              .filter((entity) =>
                entity.type === "athlete" &&
                entity.name.toLocaleLowerCase().startsWith(context.text.toLocaleLowerCase()) &&
                !seen.has(entity.id)
              )
              .forEach((entity) => {
                seen.add(entity.id);
                athleteWordingVariants(entity).forEach((wording) => {
                  const button = document.createElement("button");
                  button.id = `inline-entity-${crypto.randomUUID()}`;
                  button.type = "button";
                  button.setAttribute("role", "option");
                  button.setAttribute("aria-selected", "false");
                  button.setAttribute("aria-label", `Insert and link ${wording}`);
                  button.tabIndex = -1;
                  button.textContent = wording;
                  button.addEventListener("mousedown", (event) => event.preventDefault());
                  button.addEventListener("click", () => {
                    queryContext = context;
                    addEntity(entity, "", false, wording);
                  });
                  options.appendChild(button);
                });
              });
            hasMore = Boolean(payload.has_more);
            offset = payload.next_offset;
          }

          if (!seen.size) {
            const empty = document.createElement("span");
            empty.className = "sew-entity-loading";
            empty.textContent = `No athletes match “${context.text}”.`;
            suggestions.replaceChildren(empty);
            return;
          }

          const count = document.createElement("small");
          count.className = "sew-entity-suggestion-count";
          count.textContent = `${seen.size} matching athlete${seen.size === 1 ? "" : "s"}`;
          label.append(" · ", count);
        } catch (error) {
          if (error.name !== "AbortError") {
            const unavailable = document.createElement("span");
            unavailable.className = "sew-entity-loading";
            unavailable.textContent = "Athlete suggestions are temporarily unavailable. You can still select the wording and use the link button.";
            suggestions.replaceChildren(unavailable);
          }
        }
      }, 300);
    };

    const chainButton = editor
      .closest(".sew-working-editor")
      ?.querySelector("[data-link-entity]");

    chainButton?.addEventListener("mousedown", (event) => {
      event.preventDefault();
      savedMentionContext = selectedMentionContext() || savedMentionContext;
    });

    chainButton?.addEventListener("click", () => {
      const linkedChip = annotationAtSelection();
      if (linkedChip) {
        linkedChip.remove();
        scheduleMentionHighlights();
        updateToolbarState();
        announce("Entity unlinked.");
        return;
      }
      const context = selectedMentionContext() || savedMentionContext;
      if (context) openEntityLookup(context);
      else window.alert("Select the exact text you want to link first.");
    });

    editor.addEventListener("selectstart", () => {
      savedMentionContext = null;
    });

    editor.addEventListener("mouseup", () => {
      savedMentionContext = selectedMentionContext();
    });

    editor.addEventListener("keyup", (event) => {
      if (event.shiftKey) savedMentionContext = selectedMentionContext();
    });

    editor.addEventListener("contextmenu", (event) => {
      const context = selectedMentionContext();
      if (!context) return;
      event.preventDefault();

      document.querySelector("[data-entity-context-menu]")?.remove();
      const menu = document.createElement("div");
      menu.className = "sew-entity-context-menu";
      menu.dataset.entityContextMenu = "";
      menu.style.left = `${event.clientX}px`;
      menu.style.top = `${event.clientY}px`;

      const action = document.createElement("button");
      action.type = "button";
      action.innerHTML = '<span aria-hidden="true">🔗</span> Add entity link';
      action.addEventListener("click", () => {
        menu.remove();
        openEntityLookup(context);
      });
      menu.appendChild(action);
      document.body.appendChild(menu);
      action.focus();
    });

    editor.addEventListener("keydown", (event) => {
      const inlineOptions = [...(suggestions?.querySelectorAll(".sew-inline-entity-options button") || [])];
      if (inlineOptions.length && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
        event.preventDefault();
        recognitionActiveIndex = event.key === "ArrowDown"
          ? (recognitionActiveIndex + 1) % inlineOptions.length
          : (recognitionActiveIndex <= 0 ? inlineOptions.length - 1 : recognitionActiveIndex - 1);
        inlineOptions.forEach((button, index) => {
          const active = index === recognitionActiveIndex;
          button.setAttribute("aria-selected", String(active));
          button.classList.toggle("is-active", active);
        });
        const active = inlineOptions[recognitionActiveIndex];
        editor.setAttribute("aria-activedescendant", active.id);
        active.scrollIntoView({ block: "nearest" });
        return;
      }
      if (inlineOptions.length && event.key === "Enter" && recognitionActiveIndex >= 0) {
        event.preventDefault();
        inlineOptions[recognitionActiveIndex].click();
        return;
      }
      if (inlineOptions.length && event.key === "Escape") {
        event.preventDefault();
        recognitionController?.abort();
        suggestions.replaceChildren();
        recognitionActiveIndex = -1;
        editor.removeAttribute("aria-activedescendant");
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        document.execCommand("insertLineBreak", false);
      }
    });

    selected.addEventListener("click", (event) => {
      if (
        !event.target.matches(
          "[data-remove-entity]",
        )
      ) {
        return;
      }

      event.target
        .closest("[data-entity-id]")
        ?.remove();

      scheduleMentionHighlights();
      announce("Entity unlinked. Select wording and use the link button to add it again.");
    });

    document.addEventListener("selectionchange", () => {
      updateToolbarState();
      if (!queryContext || results.hidden) return;
      const selection = window.getSelection();
      if (!selection?.rangeCount || !editor.contains(selection.anchorNode)) return;
      if (!sameRange(selection.getRangeAt(0), queryContext.range)) {
        closeResults("The selection changed, so the previous lookup was cancelled.");
      }
    });

    editor.addEventListener("copy", (event) => {
      const context = selectedMentionContext();
      if (!context) return;
      const links = [...selected.querySelectorAll("[data-entity-id]")]
        .map((chip) => {
          const annotation = ensureChipRange(chip);
          if (!annotation || annotation.start < context.start || annotation.end > context.end) return null;
          return {
            id: chip.dataset.entityId,
            name: chip.dataset.entityName || chip.firstChild?.textContent?.trim() || "",
            type: chip.dataset.entityType || chip.querySelector("small")?.textContent || "",
            canonical_id: chip.dataset.canonicalId || "",
            canonical_url: chip.dataset.entityUrl || "",
            mention: annotation.mention,
            relative_start: annotation.start - context.start,
            relative_end: annotation.end - context.start,
          };
        })
        .filter(Boolean);
      if (!links.length) return;
      const clipboardPayload = JSON.stringify({
        token: sheetClipboardToken,
        links,
      });
      const htmlClipboard = document.createElement("span");
      htmlClipboard.dataset.cxmsEntityClipboard = encodeURIComponent(clipboardPayload);
      htmlClipboard.textContent = context.range.toString();
      event.preventDefault();
      event.clipboardData.setData("text/plain", context.range.toString());
      event.clipboardData.setData("text/html", htmlClipboard.outerHTML);
      event.clipboardData.setData(entityClipboardType, clipboardPayload);
    });

    editor.addEventListener("paste", (event) => {
      let encoded = event.clipboardData.getData(entityClipboardType);
      if (!encoded) {
        const html = document.createElement("template");
        html.innerHTML = event.clipboardData.getData("text/html");
        const fallback = html.content.querySelector("[data-cxms-entity-clipboard]");
        if (fallback?.dataset.cxmsEntityClipboard) {
          try {
            encoded = decodeURIComponent(fallback.dataset.cxmsEntityClipboard);
          } catch (_error) {
            return;
          }
        }
      }
      if (!encoded) return;
      let payload;
      try {
        payload = JSON.parse(encoded);
      } catch (_error) {
        return;
      }
      if (payload.token !== sheetClipboardToken || !Array.isArray(payload.links)) return;
      const pastedText = event.clipboardData.getData("text/plain");
      const pasteStart = selectedOffsets()?.start ?? editor.innerText.length;
      event.preventDefault();
      event.stopImmediatePropagation();
      document.execCommand("insertText", false, pastedText);

      // Let each editor synchronise its plain-text baseline before attaching
      // annotations. Otherwise the insertion diff shifts a newly created range
      // for a second time and immediately treats the copied link as stale.
      editor.dispatchEvent(new Event("input", { bubbles: true }));

      payload.links
        .filter((entity) =>
          Number.isInteger(entity.relative_start) &&
          Number.isInteger(entity.relative_end) &&
          entity.relative_start >= 0 &&
          entity.relative_end > entity.relative_start &&
          pastedText.slice(entity.relative_start, entity.relative_end) === entity.mention
        )
        .forEach((entity) => {
          addEntity({
            ...entity,
            annotation_start: pasteStart + entity.relative_start,
            annotation_end: pasteStart + entity.relative_end,
          }, entity.mention, true);
        });
      announce("Copied entity links were retained within this stat sheet.");
    }, true);

    document.addEventListener(
      "pointerdown",
      (event) => {
        if (
          editor.contains(event.target) ||
          results.contains(event.target) ||
          event.target.closest?.("[data-entity-context-menu]")
        ) {
          return;
        }

        document.querySelector("[data-entity-context-menu]")?.remove();
        closeResults();
      },
    );
  };

  document
    .querySelectorAll("[data-entity-control]")
    .forEach(initialiseEntityControl);

  // Ensure a newly added statistic is initialised before its first keystroke.
  // The focus fallback also lets a partially constructed block retry instead
  // of remaining inert after an early observer delivery.
  document.addEventListener("focusin", (event) => {
    const editor = event.target.closest?.("[data-review-editor], [data-editor]");
    const block = editor?.closest("[data-review-block], [data-content-block]");
    block
      ?.querySelectorAll("[data-entity-control]")
      .forEach(initialiseEntityControl);
  });

  document.addEventListener("sports-editorial:block-added", (event) => {
    event.target
      .querySelectorAll?.("[data-entity-control]")
      .forEach(initialiseEntityControl);
  });

  new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (!(node instanceof Element)) return;

        if (node.matches("[data-entity-control]")) {
          initialiseEntityControl(node);
        }

        node
          .querySelectorAll?.("[data-entity-control]")
          .forEach(initialiseEntityControl);
      });
    });
  }).observe(document.body, {
    childList: true,
    subtree: true,
  });

  document
    .querySelectorAll("form[data-confirm]")
    .forEach((form) => {
      form.addEventListener("submit", (event) => {
        if (!window.confirm(form.dataset.confirm)) {
          event.preventDefault();
        }
      });
    });

  const setAccepted = (block, accepted) => {
    const input = block.querySelector(
      "[data-accepted-input]",
    );

    const toggle = block.querySelector(
      "[data-toggle-accepted]",
    );

    const editor = block.querySelector(
      "[data-review-editor]",
    );

    if (!input || !toggle || !editor) return;

    input.value = accepted ? "1" : "0";
    block.dataset.accepted = accepted ? "1" : "0";

    block.classList.toggle(
      "is-accepted",
      accepted,
    );

    block.classList.toggle(
      "needs-review",
      !accepted,
    );

    editor.contentEditable = accepted
      ? "false"
      : "true";

    block.querySelector(
      "[data-review-status]",
    ).textContent = accepted
      ? "Accepted · locked"
      : "Needs review";

    toggle.textContent = accepted
      ? "Unlock"
      : "Accept and lock";

    toggle.classList.toggle(
      "sew-button--danger",
      accepted,
    );

    toggle.classList.toggle(
      "sew-button--primary",
      !accepted,
    );

    block
      .querySelectorAll(
        [
          "[data-review-format]",
          "[data-remove-entity]",
          "[data-entity-type]",
          "[data-entity-search]",
        ].join(", "),
      )
      .forEach((control) => {
        control.disabled = accepted;
      });

    block
      .querySelectorAll(
        "[data-entity-id] label input",
      )
      .forEach((control) => {
        control.readOnly = accepted;
      });

    updateAcceptanceSummary();
  };

  const updateAcceptanceSummary = () => {
    const contentBlocks = [
      ...document.querySelectorAll(
        "[data-review-block]",
      ),
    ];

    const accepted = contentBlocks.filter(
      (block) =>
        block.dataset.accepted === "1",
    ).length;

    const acceptedCount =
      document.querySelector(
        "[data-accepted-count]",
      );

    const statCount =
      document.querySelector("[data-stat-count]");

    if (acceptedCount) {
      acceptedCount.textContent =
        String(accepted);
    }

    if (statCount) {
      statCount.textContent =
        String(contentBlocks.length);
    }
  };

  document.addEventListener("click", (event) => {
    const toggle = event.target.closest(
      "[data-toggle-accepted]",
    );

    if (toggle) {
      const block = toggle.closest(
        "[data-review-block]",
      );

      const invalid = [
        ...block.querySelectorAll(
          "[data-entity-id]",
        ),
      ].filter(
        (chip) => !chip.dataset.canonicalId,
      );

      if (
        block.dataset.accepted !== "1" &&
        invalid.length
      ) {
        window.alert(
          "Fix entity links without canonical FIS IDs before accepting this statistic.",
        );
        return;
      }

      setAccepted(
        block,
        block.dataset.accepted !== "1",
      );
    }

    const remove = event.target.closest(
      "[data-remove-review-block]",
    );

    if (remove) {
      const blockToRemove = remove.closest("[data-review-block]");
      const removalConfirmed =
        blockToRemove.dataset.blockType === "section" ||
        window.confirm("Remove this statistic from the stat sheet?");

      if (removalConfirmed) {
        blockToRemove.remove();
        renumberReviewBlocks();
        updateAcceptanceSummary();
      }
    }
  });

  document
    .querySelector("[data-accept-all]")
    ?.addEventListener("click", () => {
      const invalid = [
        ...document.querySelectorAll(
          "[data-review-block][data-block-type='stat'] [data-entity-id]",
        ),
      ].filter(
        (chip) => !chip.dataset.canonicalId,
      );

      if (invalid.length) {
        window.alert(
          `${invalid.length} entity links need a canonical FIS ID before the statistics can be accepted.`,
        );
        return;
      }

      if (
        !window.confirm(
          "Validate entity links, then accept and lock every statistic and sub-heading?",
        )
      ) {
        return;
      }

      document
        .querySelectorAll(
          "[data-review-block]",
        )
        .forEach((block) => {
          setAccepted(block, true);
        });
    });

  document.addEventListener("click", (event) => {
    const checkLinks = event.target.closest("[data-check-block-entities]");
    if (!checkLinks) return;
    const block = checkLinks.closest("[data-review-block], [data-content-block]");
      const chips = [
        ...block.querySelectorAll(
          "[data-entity-id]",
        ),
      ];

      const invalid = chips.filter(
        (chip) => !chip.dataset.canonicalId,
      );

      const links = [
        ...new Set(
          chips
            .map(
              (chip) =>
                chip.dataset.entityUrl,
            )
            .filter(Boolean),
        ),
      ];

      links.forEach((url) => {
        window.open(
          url,
          "_blank",
          "noopener",
        );
      });

      window.alert(
        `${chips.length - invalid.length} links in this statistic have canonical IDs. ` +
          `${invalid.length} need attention.` +
          `${links.length ? ` Opened ${links.length} source pages.` : ""}`,
      );
    });

  document
    .querySelectorAll("[data-confirm-button]")
    .forEach((button) => {
      button.addEventListener("click", (event) => {
        if (
          !window.confirm(
            button.dataset.confirmButton,
          )
        ) {
          event.preventDefault();
        }
      });
    });

  const reviewList = document.querySelector(
    "[data-review-list]",
  );

  const renumberReviewBlocks = () => {
    const counts = {
      stat: 0,
      section: 0,
    };

    reviewList
      ?.querySelectorAll("[data-review-block]")
      .forEach((block) => {
        counts[block.dataset.blockType] += 1;

        block.querySelector(
          "[data-review-label]",
        ).textContent =
          `${
            block.dataset.blockType === "section"
              ? "Head"
              : "Stat"
          } ${counts[block.dataset.blockType]}`;
      });
  };

  const makeReviewBlock = (type) => {
    const id = crypto.randomUUID();
    const block = document.createElement("article");

    block.className =
      `sew-stat-card sew-stat-card--${type} needs-review`;

    block.dataset.reviewBlock = "";
    block.dataset.blockType = type;
    block.dataset.accepted = "0";
    block.draggable = false;

    const entities =
      type === "stat"
        ? `
          <div
            class="sew-entity-autocomplete sew-entity-autocomplete--inline-only"
            data-entity-control
            data-field-name="entity_ids_${id}"
            data-mention-prefix="entity_mention_${id}_"
          >
            <div
              class="sew-selected-entities"
              data-selected-entities
              hidden
            ></div>
            <div
              class="sew-entity-suggestions"
              data-entity-suggestions
              aria-live="polite"
            ></div>
            <div
              class="sew-entity-results"
              data-entity-results
              hidden
            ></div>
          </div>
        `
        : "";

    const acceptedInput = `
          <input
            type="hidden"
            name="accepted_${id}"
            value="0"
            data-accepted-input
          >
        `;

    const accept = `
          <button
            class="sew-button sew-button--primary sew-button--small"
            type="button"
            data-toggle-accepted
          >
            Accept and lock
          </button>
        `;

    block.innerHTML = `
      <header>
        <div class="sew-card-header-actions">
          <span
            class="sew-validation"
            data-review-status
          >
            Needs review
          </span>
          ${type === "stat" ? `<button class="sew-button sew-button--small" type="button" data-check-block-entities>Check links</button>` : ""}
          ${accept}
          <button
            class="sew-button sew-button--danger sew-button--small"
            type="button"
            data-remove-review-block
          >
            Remove
          </button>
        </div>
      </header>

      <input
        type="hidden"
        name="content_id"
        value="${id}"
      >

      <input
        type="hidden"
        name="content_type"
        value="${type}"
      >

      ${acceptedInput}

      <div class="sew-content-editor-row">
        <div class="sew-content-block-label">
          <span
            class="sew-drag"
            title="Drag to reorder"
            draggable="true"
          >
            ⋮⋮
          </span>
          <span data-review-label></span>
        </div>

        <div class="sew-content-editor-body">
          <div class="sew-working-editor">
            <div class="sew-mini-toolbar">
              <button
                type="button"
                data-review-format="bold"
              >
                <strong>B</strong>
              </button>

              <button
                type="button"
                data-review-format="italic"
              >
                <em>I</em>
              </button>

              ${type === "stat" ? `<button type="button" data-link-entity aria-label="Add entity link" title="Add entity link"><span aria-hidden="true">🔗</span></button>` : ""}
            </div>

            <div
              class="sew-rich-editor"
              contenteditable="true"
              role="textbox"
              aria-label="${
                type === "section"
                  ? "Sub-heading"
                  : "Statistic"
              } wording"
              data-review-editor
            ></div>

            <textarea
              name="edited_text_${id}"
              hidden
              data-review-input
              data-content-input
            ></textarea>
          </div>

          <details class="sew-original">
            <summary>
              View original researcher wording
            </summary>
            <div class="sew-rendered-content"></div>
          </details>

          ${entities}
        </div>
      </div>
    `;

    return block;
  };

  document
    .querySelectorAll("[data-add-review-block]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        const block = makeReviewBlock(
          button.dataset.addReviewBlock,
        );

        document
          .querySelector("[data-review-empty]")
          ?.remove();

        reviewList.appendChild(block);

        initialiseReviewBlock(block);

        block
          .querySelectorAll("[data-entity-control]")
          .forEach(initialiseEntityControl);

        renumberReviewBlocks();
        updateAcceptanceSummary();

        block
          .querySelector("[data-review-editor]")
          .focus();
      });
    });

  let draggedReviewBlock;

  reviewList?.addEventListener(
    "dragstart",
    (event) => {
      const handle =
        event.target.closest(".sew-drag");

      draggedReviewBlock =
        handle?.closest("[data-review-block]");

      if (!draggedReviewBlock) {
        event.preventDefault();
      }
    },
  );

  reviewList?.addEventListener(
    "dragover",
    (event) => {
      if (!draggedReviewBlock) return;

      event.preventDefault();

      const target = event.target.closest(
        "[data-review-block]",
      );

      if (
        target &&
        target !== draggedReviewBlock
      ) {
        const box =
          target.getBoundingClientRect();

        reviewList.insertBefore(
          draggedReviewBlock,
          event.clientY <
            box.top + box.height / 2
            ? target
            : target.nextSibling,
        );
      }
    },
  );

  reviewList?.addEventListener(
    "dragend",
    () => {
      draggedReviewBlock = null;
      renumberReviewBlocks();
    },
  );

  const reviewForm = document.querySelector(
    "[data-review-form]",
  );

  let formDirty = false;
  let formSubmitting = false;

  reviewForm?.addEventListener(
    "input",
    () => {
      formDirty = true;
    },
  );

  reviewForm?.addEventListener(
    "change",
    () => {
      formDirty = true;
    },
  );

  reviewForm?.addEventListener(
    "click",
    (event) => {
      if (
        event.target.closest(
          [
            "[data-toggle-accepted]",
            "[data-accept-all]",
            "[data-remove-review-block]",
            "[data-add-review-block]",
            "[data-remove-entity]",
          ].join(", "),
        )
      ) {
        formDirty = true;
      }
    },
  );

  reviewForm?.addEventListener(
    "submit",
    (event) => {
      if (
        !event.submitter ||
        formSubmitting
      ) {
        event.preventDefault();
        return;
      }

      formSubmitting = true;
      formDirty = false;

      renumberReviewBlocks();

      reviewForm
        .querySelectorAll("button[type='submit']")
        .forEach((button) => {
          if (button !== event.submitter) {
            button.disabled = true;
          }
        });

      event.submitter.setAttribute(
        "aria-disabled",
        "true",
      );
    },
  );

  reviewForm?.addEventListener(
    "keydown",
    (event) => {
      if (
        event.key !== "Enter" ||
        event.target.matches(
          [
            "textarea",
            "[contenteditable='true']",
            "[data-entity-lookup]",
            "button[type='submit']",
          ].join(", "),
        )
      ) {
        return;
      }

      event.preventDefault();
    },
  );

  document
    .querySelector("[data-close-review]")
    ?.addEventListener("click", (event) => {
      if (
        formDirty &&
        !window.confirm(
          "Close without saving your changes?",
        )
      ) {
        event.preventDefault();
      }
    });

  reviewList?.addEventListener(
    "dragend",
    () => {
      formDirty = true;
    },
  );

  document.querySelectorAll("[data-track-note-change]").forEach((field) => {
    const initialValue = field.value;
    const badge = field.closest("label")?.querySelector("[data-note-change]");
    field.addEventListener("input", () => {
      if (badge) badge.hidden = field.value === initialValue;
    });
  });

  renumberReviewBlocks();
  updateAcceptanceSummary();
})();
