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
    let savedMentionContext = null;

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

          // The chip and entity ID are one relationship. Remove them together
          // when the exact confirmed wording no longer exists, otherwise the
          // stale chip blocks the editor from linking this entity again.
          chip.remove();
        });

      scheduleMentionHighlights();
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
            }
          : null;
      }
      return null;
    };

    const addEntity = (entity) => {
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

      const mentionText = queryContext?.text || entity.name;

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
    });

    const openEntityLookup = (context) => {
      if (!context || !editor.isContentEditable) return;
      queryContext = context;
      activeIndex = -1;
      nextOffset = 0;

      const label = document.createElement("label");
      label.className = "sew-entity-lookup-label";
      label.textContent = `Link “${context.text}” to an entity`;

      const lookup = document.createElement("input");
      lookup.type = "search";
      lookup.dataset.entityLookup = "";
      lookup.placeholder = "Search athlete, country or competition";
      lookup.autocomplete = "off";
      lookup.setAttribute("role", "combobox");
      lookup.setAttribute("aria-expanded", "true");

      const options = document.createElement("div");
      options.dataset.entityOptions = "";
      options.id = `${results.id}-options`;
      options.setAttribute("role", "listbox");
      options.innerHTML = '<span class="sew-entity-loading">Type at least two characters.</span>';
      lookup.setAttribute("aria-controls", options.id);

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

      results.replaceChildren(label, lookup, options);
      results.hidden = false;
      lookup.focus({ preventScroll: true });
    };

    const chainButton = editor
      .closest(".sew-working-editor")
      ?.querySelector("[data-link-entity]");

    chainButton?.addEventListener("mousedown", (event) => {
      event.preventDefault();
      savedMentionContext = selectedMentionContext() || savedMentionContext;
    });

    chainButton?.addEventListener("click", () => {
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
    });

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
              ? "Head"
              : "Stat"
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

  renumberReviewBlocks();
  updateAcceptanceSummary();
})();
