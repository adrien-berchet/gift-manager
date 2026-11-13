/**
 * Grid row actions
 * Single definition of the Grid.js row actions (icons, button variants, labels, required
 * permissions) and the markup of the action bar, shared by GridUtils.actionButtonsFormatter and
 * PermissionUtils.permissionAwareActionFormatter. The bar matches the dashboard gift plan card:
 * quiet utility buttons, one primary Edit action, and an overflow menu for Share and Delete.
 */

(function (window) {
    "use strict";

    // Permission level constants (must match Django PermissionLevel)
    const PERMISSION_LEVELS = Object.freeze({
        NONE: 0,
        VIEWER: 10,
        EDITOR: 20,
        OWNER: 30,
    });

    /**
     * Row action definitions.
     * - action: data-action value handled by the offcanvas, detail and delete flows
     * - urlAttribute: extra data attribute carrying the URL for those flows
     * - variant: Bootstrap button variant for inline actions
     * - labeled: keeps a visible text label where space allows
     * - menu: rendered in the overflow menu instead of the inline bar
     * - order: position in the bar or menu, so every page lists actions the same way
     * - titleKey / title: translated label in window.gridTranslations, and its English fallback
     */
    const ACTION_CONFIG = Object.freeze({
        give: Object.freeze({
            action: "create",
            urlAttribute: "data-create-url",
            icon: "fa-hand-holding-heart",
            variant: "btn-outline-primary",
            labeled: true,
            menu: false,
            order: 10,
            titleKey: "actionGive",
            title: "Give",
            requiredPermission: PERMISSION_LEVELS.EDITOR,
        }),
        details: Object.freeze({
            action: "detail",
            urlAttribute: "data-detail-url",
            icon: "fa-eye",
            variant: "btn-outline-secondary",
            labeled: false,
            menu: false,
            order: 20,
            titleKey: "actionDetails",
            title: "Details",
            requiredPermission: PERMISSION_LEVELS.VIEWER,
        }),
        expand: Object.freeze({
            action: "expand",
            urlAttribute: "data-detail-url",
            icon: "fa-chevron-down",
            variant: "btn-outline-secondary",
            labeled: false,
            menu: false,
            order: 25,
            titleKey: "actionExpand",
            title: "Expand",
            requiredPermission: PERMISSION_LEVELS.VIEWER,
        }),
        duplicate: Object.freeze({
            action: "create",
            urlAttribute: "data-create-url",
            icon: "fa-copy",
            variant: "btn-outline-secondary",
            labeled: false,
            menu: false,
            order: 30,
            titleKey: "actionDuplicate",
            title: "Duplicate",
            requiredPermission: PERMISSION_LEVELS.VIEWER,
        }),
        edit: Object.freeze({
            action: "edit",
            urlAttribute: "data-edit-url",
            icon: "fa-pen",
            lockedIcon: "fa-lock",
            lockedTitleKey: "editNotPermitted",
            lockedTitle: "You do not have permission to edit this item",
            variant: "btn-primary",
            labeled: true,
            menu: false,
            order: 40,
            titleKey: "actionEdit",
            title: "Edit",
            requiredPermission: PERMISSION_LEVELS.EDITOR,
        }),
        share: Object.freeze({
            action: "share",
            urlAttribute: null,
            icon: "fa-share-nodes",
            menu: true,
            order: 50,
            titleKey: "actionShare",
            title: "Share",
            requiredPermission: PERMISSION_LEVELS.OWNER,
        }),
        delete: Object.freeze({
            action: "delete",
            urlAttribute: "data-delete-url",
            icon: "fa-trash",
            danger: true,
            menu: true,
            order: 60,
            titleKey: "actionDelete",
            title: "Delete",
            requiredPermission: PERMISSION_LEVELS.OWNER,
        }),
    });

    // What "Delete" does for the user on a row, as computed by the server
    // (PermissionService.delete_mode_for): the object is deleted, only the user's own access is
    // removed ("leave", after naming a new owner for "handover"), or nothing is possible.
    const DELETE_MODES = Object.freeze({
        DELETE: "delete",
        LEAVE: "leave",
        HANDOVER: "handover",
        NONE: "none",
    });
    const LEAVE_ACCESS_QUERY = "intent=leave_access";

    // The delete action of a row whose deletion only removes the user's own access. It goes
    // through the same confirmation flow as Delete, which reads the intent from the URL.
    const LEAVE_ACTIONS = Object.freeze({
        [DELETE_MODES.LEAVE]: Object.freeze({
            ...ACTION_CONFIG.delete,
            icon: "fa-user-minus",
            titleKey: "actionLeave",
            title: "Remove my access",
        }),
        [DELETE_MODES.HANDOVER]: Object.freeze({
            ...ACTION_CONFIG.delete,
            icon: "fa-user-minus",
            titleKey: "actionHandover",
            title: "Hand over and remove my access",
        }),
    });

    let deleteModes = null;
    let deleteReasons = null;

    /**
     * Replace the delete modes of the listed rows ({entityId: mode}) and the reasons of the
     * blocked ones ({entityId: reason}), e.g. after a refresh.
     */
    function setDeleteModes(modes, reasons) {
        deleteModes = modes && typeof modes === "object" ? modes : null;
        deleteReasons = reasons && typeof reasons === "object" ? reasons : {};
    }

    /** Parsed content of a json_script element, or null when the page has none. */
    function readJsonScript(elementId) {
        const element = document.getElementById(elementId);
        if (!element) return null;
        try {
            return JSON.parse(element.textContent) || {};
        } catch (error) {
            return {};
        }
    }

    /**
     * Delete mode of a row, or null when the page provides none (permission levels then decide).
     * Modes and reasons come from includes/grid_delete_modes.html, rendered next to the grid data.
     */
    function deleteModeFor(id) {
        if (deleteModes === null) {
            deleteModes = readJsonScript("user-delete-modes");
            if (deleteModes === null) return null;
            deleteReasons = readJsonScript("user-delete-reasons") || {};
        }
        return deleteModes[id] || DELETE_MODES.NONE;
    }

    /** Why a row can be neither deleted nor left, when the server gave a reason. */
    function deleteReasonFor(id) {
        return (deleteReasons && deleteReasons[id]) || "";
    }

    /** Add the leave intent to a delete URL. */
    function leaveUrl(url) {
        return url + (url.includes("?") ? "&" : "?") + LEAVE_ACCESS_QUERY;
    }

    function escapeHtml(value) {
        return window.GMUtils.escapeHtml(value);
    }

    function escapeAttribute(value) {
        return window.GMUtils.escapeAttribute(value);
    }

    function safeUrl(value) {
        return window.GMUtils.safeUrl(value);
    }

    function translate(key, fallback) {
        const translations = window.gridTranslations || {};
        return translations[key] || fallback;
    }

    function actionTitle(type) {
        const config = ACTION_CONFIG[type];
        return config ? translate(config.titleKey, config.title) : "";
    }

    /**
     * Resolve the actions a row displays, with their URLs, in the shared order.
     *
     * @param {Object} urls - URL templates ('/objects/{id}/') or functions (row) => URL
     * @param {Array} actions - Action names, or {type, condition, id} objects
     * @param {Object} row - Grid.js row
     * @param {*} id - Entity ID substituted into URL templates
     * @returns {Array} [{type, config, url}] sorted by config.order
     */
    function resolveActions(urls, actions, row, id) {
        return actions
            .filter((action) => typeof action === "string" || !action.condition || action.condition(row))
            .map((action) => {
                const type = typeof action === "string" ? action : action.type;
                const config = ACTION_CONFIG[type];
                const urlTemplate = urls[type];
                if (!config || !urlTemplate) return null;
                const actionId = typeof action === "object" ? action.id : null;
                const url =
                    typeof urlTemplate === "function"
                        ? urlTemplate(row)
                        : urlTemplate.replace("{id}", actionId || id);
                return url ? { type, config, url } : null;
            })
            .filter(Boolean)
            .sort((left, right) => left.config.order - right.config.order);
    }

    function commonAttributes(item, safeId, permissionLevel) {
        const permissionAttribute =
            permissionLevel === null ? "" : ` data-permission-level="${escapeAttribute(permissionLevel)}"`;
        return `data-action-type="${escapeAttribute(item.type)}" data-entity-id="${safeId}"${permissionAttribute}`;
    }

    function iconHtml(icon, extraClass = "") {
        return `<i class="fas ${escapeAttribute(icon)}${extraClass}" aria-hidden="true"></i>`;
    }

    function inlineButtonHtml(item, safeId, permissionLevel, allowed) {
        const { config } = item;
        const title = translate(config.titleKey, config.title);
        const safeTitle = escapeAttribute(title);
        const attributes = commonAttributes(item, safeId, permissionLevel);

        if (!allowed && config.lockedIcon) {
            // Same affordance as the dashboard card: a quiet lock instead of the action
            const lockedTitle = escapeAttribute(translate(config.lockedTitleKey, config.lockedTitle));
            return `<button type="button" class="btn btn-sm btn-outline-secondary quick-action-btn grid-action grid-action--locked"
                    disabled title="${lockedTitle}" aria-label="${safeTitle}" ${attributes}>${iconHtml(config.lockedIcon)}</button>`;
        }

        const labelClass = config.labeled ? " grid-action--labeled" : "";
        const label = config.labeled
            ? `<span class="btn-text d-none d-lg-inline">${escapeHtml(title)}</span>`
            : "";
        const classes = `btn btn-sm ${config.variant} quick-action-btn grid-action${labelClass}`;

        if (!allowed) {
            const deniedTitle = escapeAttribute(
                translate("actionNotPermitted", "You do not have permission to perform this action.")
            );
            return `<button type="button" class="${classes}" disabled title="${deniedTitle}"
                    aria-label="${safeTitle}" ${attributes}>${iconHtml(config.icon)}${label}</button>`;
        }

        const href = safeUrl(item.url);
        const urlAttribute = config.urlAttribute ? ` ${config.urlAttribute}="${href}"` : "";
        // Labeled buttons already show their name, so only icon-only ones get a tooltip
        const tooltip = config.labeled ? "" : ' data-bs-toggle="tooltip" data-bs-placement="top"';
        return `<a href="${href}" class="${classes}" title="${safeTitle}" aria-label="${safeTitle}"
                  data-action="${escapeAttribute(config.action)}"${urlAttribute} ${attributes}${tooltip}>${iconHtml(config.icon)}${label}</a>`;
    }

    function menuItemHtml(item, safeId, permissionLevel) {
        const { config } = item;
        const title = translate(config.titleKey, config.title);
        const href = safeUrl(item.url);
        const urlAttribute = config.urlAttribute ? ` ${config.urlAttribute}="${href}"` : "";
        const dangerClass = config.danger ? " grid-action-menu-item--danger" : "";
        return `<li><a href="${href}" class="dropdown-item grid-action-menu-item${dangerClass}"
                   data-action="${escapeAttribute(config.action)}"${urlAttribute} ${commonAttributes(item, safeId, permissionLevel)}>${iconHtml(config.icon, " fa-fw")}<span>${escapeHtml(title)}</span></a></li>`;
    }

    /** A Delete entry that cannot be used, with the reason below it. */
    function blockedMenuItemHtml(item, reason) {
        const title = translate(item.config.titleKey, item.config.title);
        return `<li><span class="dropdown-item disabled grid-action-menu-item" aria-disabled="true"
                   data-action-type="${escapeAttribute(item.type)}">${iconHtml(item.config.icon, " fa-fw")}<span>${escapeHtml(title)}</span></span>
                <span class="dropdown-item-text grid-action-menu-reason">${escapeHtml(reason)}</span></li>`;
    }

    function menuHtml(items, safeId, permissionLevel, blockedDeleteReason = "") {
        if (items.length === 0) return "";
        const moreActions = escapeAttribute(translate("moreActions", "More actions"));
        // A fixed popper escapes the clipping of the Grid.js wrapper and of the card itself
        return `<div class="dropdown grid-action-menu">
                <button type="button" class="btn btn-sm btn-outline-secondary quick-action-btn grid-action grid-action-menu-toggle"
                        data-bs-toggle="dropdown" data-bs-popper-config='{"strategy":"fixed"}'
                        aria-expanded="false" title="${moreActions}" aria-label="${moreActions}">${iconHtml("fa-ellipsis")}</button>
                <ul class="dropdown-menu dropdown-menu-end grid-action-menu-list">${items
                    .map((item) =>
                        item.type === "delete" && blockedDeleteReason
                            ? blockedMenuItemHtml(item, blockedDeleteReason)
                            : menuItemHtml(item, safeId, permissionLevel)
                    )
                    .join("")}</ul>
            </div>`;
    }

    /**
     * Build the action bar markup for one row.
     *
     * @param {Object} options
     * @param {Object} options.urls - URL templates or functions per action type
     * @param {Array} options.actions - Action names or {type, condition, id} objects
     * @param {Object} options.row - Grid.js row
     * @param {*} options.id - Entity ID
     * @param {number|null} [options.permissionLevel] - User permission on the entity; null skips
     *        permission checks (every listed action is available)
     * @returns {string} HTML of the action bar
     */
    function renderActionBar({ urls, actions, row, id, permissionLevel = null }) {
        const safeId = escapeAttribute(id);
        // With permission checks on, the server's delete mode decides what Delete does
        const deleteMode = permissionLevel === null ? null : deleteModeFor(id);
        const isAllowed = (item) => {
            if (permissionLevel === null) return true;
            if (item.type === "delete" && deleteMode !== null) return deleteMode !== DELETE_MODES.NONE;
            return permissionLevel >= item.config.requiredPermission;
        };
        const items = resolveActions(urls, actions, row, id).map((item) => {
            const leaveConfig = item.type === "delete" ? LEAVE_ACTIONS[deleteMode] : null;
            return leaveConfig ? { ...item, config: leaveConfig, url: leaveUrl(item.url) } : item;
        });

        const inline = items
            .filter((item) => !item.config.menu)
            .map((item) => inlineButtonHtml(item, safeId, permissionLevel, isAllowed(item)));
        // Overflow actions the user may not use are hidden rather than disabled, except a
        // Delete that someone who can edit the row would expect: it says why it is blocked
        const blockedDeleteReason =
            deleteMode === DELETE_MODES.NONE && permissionLevel >= PERMISSION_LEVELS.EDITOR
                ? deleteReasonFor(id)
                : "";
        const menu = menuHtml(
            items.filter(
                (item) =>
                    item.config.menu &&
                    (isAllowed(item) || (item.type === "delete" && blockedDeleteReason))
            ),
            safeId,
            permissionLevel,
            blockedDeleteReason
        );
        const permissionAttribute =
            permissionLevel === null ? "" : ` data-permission-level="${escapeAttribute(permissionLevel)}"`;

        return `<div class="quick-actions-container grid-action-bar"${permissionAttribute}>${inline.join("")}${menu}</div>`;
    }

    window.GridActions = {
        PERMISSION_LEVELS: PERMISSION_LEVELS,
        ACTION_CONFIG: ACTION_CONFIG,
        DELETE_MODES: DELETE_MODES,
        actionTitle: actionTitle,
        setDeleteModes: setDeleteModes,
        renderActionBar: renderActionBar,
    };
})(window);
