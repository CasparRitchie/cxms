(() => {
  const editableEntityHighlightRanges = new Map();

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

    const normaliseMarkup = (value) =>
      value
        .replace(/\s+/g, " ")
        .replace(/> </g, "><")
        .trim();

    const editorMarkup = () => {
      const clone = editor.cloneNode(true);

      clone.querySelectorAll("[data-entity-ref]").forEach((tag) => {
        tag.replaceWith(document.createTextNode(tag.textContent));
      });

      return clone.innerHTML;
    };

    const sessionStartMarkup = normaliseMarkup(editorMarkup());

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
            headerActions.querySelector("[data-remove-review-block]"),
          );
        } else {
          block.querySelector("header")?.appendChild(badge);
        }
      }

      const currentMarkup = normaliseMarkup(editorMarkup());
      const changedThisSession =
        sessionStartMarkup !== currentMarkup;
      const differsFromResearcher =
        normaliseMarkup(original.innerHTML) !== currentMarkup;

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
            "Formatting changed; wording is unchanged.",
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

  const entityDisplayOptions = (entity) => {
    const name = String(entity.name || "").trim();

    if (entity.type !== "country") {
      return name ? [{ label: name, value: name }] : [];
    }

    const code = String(
      entity.country_code || entity.canonical_id || "",
    ).trim();

    const seen = new Set();

    return [code, name]
      .filter((value) => {
        const key = value.toLocaleLowerCase();

        if (!value || seen.has(key)) return false;

        seen.add(key);
        return true;
      })
      .map((value) => ({
        label: value,
        value,
      }));
  };

  const initialiseEntityControl = (control) => {
    if (control.dataset.entityInitialised) return;

    control.dataset.entityInitialised = "true";

    const results = control.querySelector("[data-entity-results]");
    const selected = control.querySelector(
      "[data-selected-entities]",
    );

    const editor = control
      .closest("[data-review-block], [data-content-block]")
      ?.querySelector("[data-review-editor], [data-editor]");

    if (!editor || !results || !selected) return;

    editor
      .closest(".sew-working-editor")
      ?.appendChild(results);

    let timer;
    let controller;
    let highlightFrame;
    let nextOffset = 0;
    let activeIndex = -1;
    let queryContext = null;
    let suppressNextSearch = false;

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

      editor.setAttribute(
        "aria-activedescendant",
        buttons[activeIndex].id,
      );
    };

    const closeResults = () => {
      clearTimeout(timer);
      controller?.abort();
      controller = null;
      queryContext = null;
      nextOffset = 0;
      activeIndex = -1;
      results.hidden = true;
      results.replaceChildren();
      editor.removeAttribute("aria-activedescendant");
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
        const words =
          chip
            .querySelector("label input")
            ?.value.trim();

        if (!words) return;

        const walker = document.createTreeWalker(
          editor,
          NodeFilter.SHOW_TEXT,
          {
            acceptNode: (node) =>
              node.parentElement?.closest("[data-entity-ref]")
                ? NodeFilter.FILTER_REJECT
                : NodeFilter.FILTER_ACCEPT,
          },
        );

        let node;

        while ((node = walker.nextNode())) {
          const index = node.data.indexOf(words);

          if (index < 0) continue;

          const range = document.createRange();
          range.setStart(node, index);
          range.setEnd(node, index + words.length);

          ranges.push(range);
          break;
        }
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

    const validateMentionTags = () => {
      selected
        .querySelectorAll("[data-entity-id]")
        .forEach((chip) => {
          const mention =
            chip.querySelector("label input");

          if (
            !mention?.value ||
            editor.innerText.includes(mention.value)
          ) {
            return;
          }

          mention.value = "";
        });

      scheduleMentionHighlights();
    };

    const caretTextOffset = () => {
      const selection = window.getSelection();

      if (
        !selection?.rangeCount ||
        !editor.contains(selection.anchorNode)
      ) {
        return null;
      }

      const range = document.createRange();
      range.selectNodeContents(editor);

      try {
        range.setEnd(
          selection.anchorNode,
          selection.anchorOffset,
        );
      } catch {
        return null;
      }

      return range.toString().length;
    };

    const caretIsInsideExistingMention = () => {
      const caretOffset = caretTextOffset();

      if (caretOffset === null) return false;

      const editorText = editor.innerText;

      return [
        ...selected.querySelectorAll(
          "[data-entity-id] label input",
        ),
      ].some((input) => {
        const mention = input.value.trim();

        if (!mention) return false;

        let searchFrom = 0;
        let mentionOffset;

        while (
          (
            mentionOffset = editorText.indexOf(
              mention,
              searchFrom,
            )
          ) !== -1
        ) {
          const mentionEnd =
            mentionOffset + mention.length;

          if (
            caretOffset >= mentionOffset &&
            caretOffset <= mentionEnd
          ) {
            return true;
          }

          searchFrom = mentionEnd;
        }

        return false;
      });
    };

    const currentQuery = () => {
      const selection = window.getSelection();

      if (
        !selection?.rangeCount ||
        !editor.contains(selection.anchorNode)
      ) {
        return null;
      }

      const range = selection.getRangeAt(0);

      if (
        range.collapsed &&
        caretIsInsideExistingMention()
      ) {
        return null;
      }

      if (!range.collapsed) {
        const text = range.toString().trim();

        return text.length >= 2 && text.length <= 80
          ? {
              text,
              range: range.cloneRange(),
              replace: false,
            }
          : null;
      }

      if (
        selection.anchorNode?.nodeType !==
        Node.TEXT_NODE
      ) {
        return null;
      }

      const before =
        selection.anchorNode.data.slice(
          0,
          selection.anchorOffset,
        );

      const match = before.match(
        /[\p{L}\p{M}'’.-]{2,}$/u,
      );

      // Keep ordinary prose unobstructed: automatic inline lookup is for
      // capitalised entity wording. Users can still select any exact wording
      // (including lower-case text) to request an entity match explicitly.
      if (
        !match ||
        !/^\p{Lu}/u.test(match[0])
      ) {
        return null;
      }

      const wordRange = document.createRange();

      wordRange.setStart(
        selection.anchorNode,
        selection.anchorOffset - match[0].length,
      );

      wordRange.setEnd(
        selection.anchorNode,
        selection.anchorOffset,
      );

      return {
        text: match[0],
        range: wordRange,
        replace: true,
      };
    };

    const placeCaretAtTextOffset = (offset) => {
      const selection = window.getSelection();

      if (!selection) return;

      const walker = document.createTreeWalker(
        editor,
        NodeFilter.SHOW_TEXT,
      );

      let remaining = offset;
      let node;

      while ((node = walker.nextNode())) {
        if (remaining <= node.data.length) {
          const caret = document.createRange();

          caret.setStart(node, remaining);
          caret.collapse(true);

          selection.removeAllRanges();
          selection.addRange(caret);

          return;
        }

        remaining -= node.data.length;
      }

      const caret = document.createRange();
      caret.selectNodeContents(editor);
      caret.collapse(false);

      selection.removeAllRanges();
      selection.addRange(caret);
    };

    const replaceQueryWithDisplayValue = (
      displayValue,
      replaceSelection = false,
    ) => {
      if (
        (!queryContext?.replace && !replaceSelection) ||
        !queryContext.range
      ) {
        return queryContext?.text || displayValue;
      }

      const range = queryContext.range;

      if (
        !editor.contains(
          range.commonAncestorContainer,
        )
      ) {
        return displayValue;
      }

      range.deleteContents();

      const text =
        document.createTextNode(displayValue);
      range.insertNode(text);

      const offsetRange = document.createRange();
      offsetRange.selectNodeContents(editor);
      offsetRange.setEndAfter(text);

      const caretOffset =
        offsetRange.toString().length;

      // Range insertion splits text nodes. Merge them again so subsequent
      // clicks, Home/End and arrow-key movement behave like a normal editor.
      editor.normalize();
      placeCaretAtTextOffset(caretOffset);

      return displayValue;
    };

    const addEntity = (
      entity,
      displayValue = entity.name,
      replaceSelection = false,
    ) => {
      const existingChip = selected.querySelector(
        `[data-entity-id="${entity.id}"]`,
      );

      if (existingChip && entity.type !== "country") {
        closeResults();
        editor.focus({ preventScroll: true });
        return;
      }

      editor.focus({ preventScroll: true });

      const mentionText =
        replaceQueryWithDisplayValue(
          displayValue,
          replaceSelection,
        );

      if (existingChip) {
        const mention = existingChip.querySelector(
          "label input",
        );

        if (mention) mention.value = mentionText;

        closeResults();
        scheduleMentionHighlights();
        suppressNextSearch = true;

        editor.dispatchEvent(
          new Event("input", { bubbles: true }),
        );

        return;
      }

      const chip = document.createElement("span");
      chip.className = "sew-entity-chip";
      chip.dataset.entityId = entity.id;
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
        `Remove ${entity.name}`,
      );
      remove.textContent = "×";

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

      chip.append(
        entityType,
        mentionLabel,
        remove,
        input,
      );

      selected.appendChild(chip);

      closeResults();
      scheduleMentionHighlights();

      suppressNextSearch = true;

      editor.dispatchEvent(
        new Event("input", { bubbles: true }),
      );
    };

    const appendResult = (entity) => {
      if (entity.type === "country") {
        const row = document.createElement("div");
        row.className =
          "sew-entity-country-result";
        row.setAttribute("role", "group");
        row.setAttribute(
          "aria-label",
          `${entity.name} insertion choices`,
        );

        const identity =
          document.createElement("span");
        identity.className =
          "sew-entity-country-identity";

        const code =
          entity.country_code ||
          entity.canonical_id ||
          "";

        identity.textContent = [
          entity.name,
          code,
        ]
          .filter(Boolean)
          .join(" · ");

        const actions =
          document.createElement("span");
        actions.className =
          "sew-entity-country-actions";

        entityDisplayOptions(entity).forEach(
          (option) => {
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
            button.setAttribute(
              "aria-label",
              `Insert ${option.label} for ${entity.name}`,
            );
            button.tabIndex = -1;
            button.textContent =
              `Insert ${option.label}`;

            button.addEventListener(
              "click",
              () => {
                addEntity(
                  entity,
                  option.value,
                  true,
                );
              },
            );

            actions.appendChild(button);
          },
        );

        row.append(identity, actions);
        results.appendChild(row);
        return;
      }

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

      results.appendChild(button);
    };

    const runSearch = async (
      append = false,
      context = queryContext,
    ) => {
      const query = context?.text.trim() || "";

      if (query.length < 2) {
        closeResults();
        return;
      }

      if (!append) {
        queryContext = context;
        nextOffset = 0;
        results.replaceChildren();
        activeIndex = -1;
      } else {
        results
          .querySelector("[data-show-more]")
          ?.remove();

        results
          .querySelector("[data-no-more]")
          ?.remove();
      }

      const loading =
        document.createElement("span");

      loading.className = "sew-entity-loading";
      loading.textContent = append
        ? "Loading more…"
        : "Searching…";

      results.appendChild(loading);
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
          queryContext?.text.trim() !== query
        ) {
          return;
        }

        loading.remove();

        if (
          !append &&
          !payload.results.length
        ) {
          results.innerHTML =
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
            runSearch(true, queryContext);
          });

          results.appendChild(more);
        } else if (
          append &&
          payload.results.length
        ) {
          const end =
            document.createElement("span");

          end.className = "sew-entity-loading";
          end.dataset.noMore = "";
          end.textContent = "No more results.";

          results.appendChild(end);
        }
      } catch (error) {
        if (error.name === "AbortError") return;

        results.innerHTML =
          '<span class="sew-entity-loading">Search is temporarily unavailable.</span>';
      }
    };

    const scheduleSearch = () => {
      clearTimeout(timer);

      if (!editor.isContentEditable) {
        closeResults();
        return;
      }

      const context = currentQuery();

      if (!context) {
        closeResults();
        return;
      }

      timer = setTimeout(() => {
        runSearch(false, context);
      }, 250);
    };

    results.id =
      results.id ||
      `entity-results-${crypto.randomUUID()}`;

    results.setAttribute("role", "listbox");

    editor.setAttribute(
      "aria-autocomplete",
      "list",
    );

    editor.setAttribute(
      "aria-controls",
      results.id,
    );

    unwrapMentionTags(editor);
    scheduleMentionHighlights();

    editor.addEventListener("input", () => {
      validateMentionTags();

      if (suppressNextSearch) {
        suppressNextSearch = false;
        return;
      }

      scheduleSearch();
    });

    // Only run a mouse-triggered entity search when the user has explicitly
    // selected text. Simply placing the caret inside normal prose or an
    // existing linked athlete must not reopen autocomplete.
    editor.addEventListener("mouseup", () => {
      const selection = window.getSelection();

      if (
        selection?.rangeCount &&
        !selection.isCollapsed
      ) {
        scheduleSearch();
      }
    });

    // Typing is already handled by the input event. Keyboard lookup here is
    // limited to explicit Shift + navigation-key text selection.
    editor.addEventListener("keyup", (event) => {
      const keyboardSelectionKeys = [
        "ArrowLeft",
        "ArrowRight",
        "Home",
        "End",
      ];

      if (
        event.shiftKey &&
        keyboardSelectionKeys.includes(event.key)
      ) {
        scheduleSearch();
      }
    });

    editor.addEventListener("keydown", (event) => {
      const resultsOpen = !results.hidden;
      const buttons = entityButtons();

      if (
        event.key === "ArrowDown" &&
        resultsOpen &&
        buttons.length
      ) {
        event.preventDefault();
        setActive(activeIndex + 1);
      } else if (
        event.key === "ArrowUp" &&
        resultsOpen &&
        buttons.length
      ) {
        event.preventDefault();

        setActive(
          activeIndex <= 0
            ? buttons.length - 1
            : activeIndex - 1,
        );
      } else if (
        event.key === "Enter" &&
        resultsOpen &&
        activeIndex >= 0 &&
        buttons[activeIndex]
      ) {
        event.preventDefault();
        buttons[activeIndex].click();
      } else if (
        event.key === "Enter" &&
        !resultsOpen
      ) {
        event.preventDefault();

        document.execCommand(
          "insertLineBreak",
          false,
        );
      } else if (
        event.key === "Escape" &&
        resultsOpen
      ) {
        event.preventDefault();
        closeResults();
        editor.focus({ preventScroll: true });
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
    });

    document.addEventListener(
      "pointerdown",
      (event) => {
        if (
          editor.contains(event.target) ||
          results.contains(event.target)
        ) {
          return;
        }

        closeResults();
      },
    );
  };

  document
    .querySelectorAll("[data-entity-control]")
    .forEach(initialiseEntityControl);

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
    const statistics = [
      ...document.querySelectorAll(
        "[data-review-block][data-block-type='stat']",
      ),
    ];

    const accepted = statistics.filter(
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
        String(statistics.length);
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

    if (
      remove &&
      window.confirm(
        "Remove this block from the stat sheet?",
      )
    ) {
      remove
        .closest("[data-review-block]")
        .remove();

      renumberReviewBlocks();
      updateAcceptanceSummary();
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
          "Validate entity links, then accept and lock every statistic?",
        )
      ) {
        return;
      }

      document
        .querySelectorAll(
          "[data-review-block][data-block-type='stat']",
        )
        .forEach((block) => {
          setAccepted(block, true);
        });
    });

  document
    .querySelector("[data-check-entities]")
    ?.addEventListener("click", () => {
      const chips = [
        ...document.querySelectorAll(
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
        `${chips.length - invalid.length} entity links have canonical IDs. ` +
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
              ? "Sub-heading"
              : "Statistic"
          } ${counts[block.dataset.blockType]}`;
      });
  };

  const makeReviewBlock = (type) => {
    const id = crypto.randomUUID();
    const block = document.createElement("article");

    block.className =
      `sew-stat-card sew-stat-card--${type}` +
      `${type === "stat" ? " needs-review" : ""}`;

    block.dataset.reviewBlock = "";
    block.dataset.blockType = type;
    block.dataset.accepted = "0";
    block.draggable = false;

    const entities =
      type === "stat"
        ? `
          <div
            class="sew-entity-autocomplete"
            data-entity-control
            data-field-name="entity_ids_${id}"
            data-mention-prefix="entity_mention_${id}_"
          >
            <span class="sew-cell-label">Linked</span>
            <div
              class="sew-selected-entities"
              data-selected-entities
            ></div>
            <div
              class="sew-entity-results"
              data-entity-results
              hidden
            ></div>
          </div>
        `
        : "";

    const acceptedInput =
      type === "stat"
        ? `
          <input
            type="hidden"
            name="accepted_${id}"
            value="0"
            data-accepted-input
          >
        `
        : "";

    const accept =
      type === "stat"
        ? `
          <button
            class="sew-button sew-button--primary sew-button--small"
            type="button"
            data-toggle-accepted
          >
            Accept and lock
          </button>
        `
        : "";

    block.innerHTML = `
      <header>
        <div class="sew-card-header-actions">
          <span
            class="sew-validation"
            data-review-status
          >
            ${
              type === "section"
                ? "Sub-heading · editable"
                : "Needs review"
            }
          </span>
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
            "[data-entity-search]",
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

  renumberReviewBlocks();
  updateAcceptanceSummary();
})();
