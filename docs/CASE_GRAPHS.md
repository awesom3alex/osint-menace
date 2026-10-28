# Case graphs

Open a case and choose **Case graphs**, or use **Add to graph** beside a saved finding. Choose an existing graph or create a new one. Adding the same finding to the same graph twice reuses its object. The object retains an **Open original case finding** link; editing graph details does not edit the original finding.

## Editing

- Create named graphs (up to 20 per case).
- Choose Person, Account, Organization, Domain/IP, or Evidence and select **Add object**. Each type starts with predefined fields.
- Drag objects to position them. Select an object to edit its label, type, fields, and photo in Details. The object selector also provides access to details without clicking the canvas.
- Add custom fields: text, long notes, number, date, dropdown, checkbox, or URL. Dropdown choices use `|` separators. Field names must be unique within an object. Choose **Show on graph** for fields that should appear below its label. Reorder or remove fields as needed.
- **Save fields as [type] template** stores the field definitions, without values, for new objects of that type in the current graph. Existing objects retain their fields. Templates currently belong to their graph, not the entire application.
- Upload PNG, JPEG, or WebP photos up to 10 MB. The browser normalizes them to PNG and resizes them to at most 512 pixels on the longest side. Photos are embedded in the case; graph rendering does not load remote image URLs.
- Select two objects with Shift-click and use **Connect selected pair**, or use **Connect to object** in an object's Details. Connections have editable endpoints, labels, notes, and a hypothesis/supported status. Hypotheses use dashed arrows; supported connections use solid arrows. These statuses are analyst annotations.
- Use **Pin position** to protect an object's position from dragging and automatic arrangement. Automatic arrangement runs only when requested.
- **Legend and object types** lets you edit each type's color and explanation and create custom types. The legend belongs to the graph and appears in its PNG export.
- Undo and redo retain up to 12 edits during the current session. Deleting an object also removes its connections; undo can restore them before leaving the page.

## Saving and exporting

Edits autosave after a short pause; **Save graph** also saves immediately. Leaving with unsaved changes triggers a browser warning. Concurrent edits in another tab produce a save conflict instead of silently overwriting changes; export your current graph JSON before using **Reload saved graph**.

Graph names, positions, fields, photos, templates, legends, and relationships persist in the case JSON and verified case backup ZIP. Restore brings them back with the case. PNG export includes the graph legend; JSON export captures the current graph, including unsaved edits. Graph-specific JSON import is not currently provided. PDF and Word reports can include explicitly selected graphs and saved views using Case report options. HTML reports retain their existing content; graph PNG export remains available.

Each graph supports up to 1,000 objects, 3,000 connections, 40 object types, and 80 fields per object. Graph saves are limited to 8 MB and must fit the existing 16 MB case-backup JSON limit. Large photos can reduce practical capacity. Layout performance depends on the device and relationship density.

## Dependency

Cytoscape.js 3.33.1 is bundled locally in `static/vendor/cytoscape-3.33.1.min.js`. Its MIT license notice is retained in the file. Graphs require no graph-service account, API key, React migration, or external graph database. Case access follows the application's existing access model.

## Navigation and investigation tools

- **Search graph** searches labels, types, tags, field names, and field values. Matching objects appear as buttons you can select to center the view. Combine this with object-type and hypothesis/supported filters. **Clear filters** restores the current branch/group view; **Expand all branches** also expands groups. View filters never remove saved content.
- **Right-click** an object or connection for common editing actions. Press Escape or click outside the menu to dismiss it. Object details provide the same essential actions without a mouse context menu.
- Select an object to reveal its **+ connection handle**. Drag it onto another object to create a connection, or click the handle and then the destination. The details panel's **Connect to object** control remains available.
- **Collapse outgoing branch** hides objects reachable along outgoing arrows, leaving the root visible. Expanding the branch restores them. Cycles are handled without deleting evidence. It may hide objects reachable through multiple paths; expand the graph to see the complete network again.
- **Group selected objects** puts selected objects into a named visual group. Assign more objects using the Group dropdown in Details. Group names are editable; collapse, expand, or ungroup using the Groups panel. Clicking a group on the canvas toggles it. Groups are one level deep.
- **Add annotation** creates a movable note with a visible Note field. Edit that field to explain an area of the graph. Annotations are saved and exported alongside objects.
- Possible duplicates appear in object Details when the same normalized label/type, email, username, domain, or profile URL is already present. These are suggestions, not identity verification. Choose **Merge into…** to retain conflicting fields under separate names, redirect connections, and preserve source references. Undo restores the separate objects. Objects with different photos require review before merging.
- Connections can link to multiple **supporting case findings**, with a relationship date and analyst notes. Use **Attach case finding** and **Attach evidence**, then select a linked finding to load its value, review status, notes, and screenshot attachments into **Evidence preview**. Removed case findings display as unavailable instead of being fetched from another case.
- The **mini-map** shows visible objects, connections, and the current viewport. Click it to navigate; use Fit view to see the graph again.

## Autosave and browser recovery

Edits autosave after a short pause. The save status reports progress and errors. A conflicting save in another tab pauses autosave; export JSON before reloading to retain your local edits. Validation errors pause autosave until you edit the graph again or choose Save graph.

Unfinished drafts are also stored locally in this browser, scoped to the case and graph. On reopening, **Recover draft** loads a draft for review; choose **Save graph** explicitly to save that recovered version and resume autosave. If the server graph changed, the recovery notice says so. **Discard draft** keeps the server version. Drafts from different editor tabs are stored separately. Browser recovery storage is limited; large photos may exceed it, in which case the interface warns you and server autosave/JSON export remain available. Successful saves remove that tab's completed draft.

Recovery data includes graph fields and photos in browser local storage. It is not sent to another service, but can remain on the device after the page closes. Use a trusted browser profile for case work. Case backups include saved server data, not unfinished browser drafts.

## Compact workspace menus

The graph toolbar keeps **Add to graph**, **Fit view**, **Undo**, and **Redo** close to the canvas. Use **More actions** for connecting a selection, grouping, automatic layout, expanding branches, and exporting. **Graph settings** contains rename, save, and reload. **Filters** holds type and relationship filters and their reset control; the search field stays visible.

Use **New graph** beside the graph selector to create another graph. Field values remain visible in Details; expand a field's **Field settings** to rename it, change its type, show it on the canvas, reorder it, or remove it. Object options, photos, connections, templates, groups, and help expand when needed. Selecting linked evidence opens its preview automatically. The legend and mini-map are under the canvas in **Legend & mini-map**.

Across the application, navigation is grouped into **Search** (Console, Unified Search), **Investigations** (Cases, History), **Tools** (Addons, Tool Health, OSINT Links), and **Help** (Help, Demo, version). Select a category to open its links. Escape or a click outside closes a menu. Case exports and backups are grouped separately from application navigation.


## Saved views and date exploration

Open **Saved views** in Details to name and save the current search/type/status/date filters, object positions, collapsed branches/groups, zoom, and pan. Choose a view and **Apply view** to return to it. **Update selected view** replaces its saved presentation; **Remove view** removes only the view. Objects added after a view was saved retain their current positions. Switching views does not remove objects, findings, or relationships. Up to 30 views can be stored per graph.

**Filters** includes inclusive From/To dates based on each connection's Relationship date. **Include undated relationships** controls connections without a date; it defaults on. Date/status filtering shows the endpoints of matching relationships, so disconnected objects and annotations can disappear from that view. Clear filters restores the current branch/group presentation. Filters do not alter the underlying case information; save them as a view to retain them.

## Named milestones

Open **Milestones**, enter a name, and choose **Create snapshot**. Current edits must save successfully first. Snapshots contain the whole graph, including objects, photos, fields, connections, layouts, groups, legends, saved views, and report settings. They survive page reloads and case backup/restore. They do not copy or restore the case's original findings or screenshot files.

Choose a snapshot and **Restore snapshot** to restore it after confirmation. A **Before restoring…** snapshot preserves the graph being replaced. Restoring resets transient filters; saved views remain available to apply. Up to 10 snapshots fit within the graph's existing 8 MB and case's 16 MB limits. Keep a free slot for the automatic pre-restore copy; use **Remove snapshot** to free space when needed. Milestone management checks the current graph revision to prevent another tab's changes from being overwritten.

## Graphs in case reports

Under **More actions → Case report options**, enable **Include this graph in case PDF and Word reports** and choose Full graph or a saved view. Full graph includes all objects and expands hidden branches/groups. A saved view includes only its matching visible content and saved arrangement. Report downloads save current edits first; other report download links use the last saved selection.

Reports include a locally rendered figure, the graph legend and relationship styles, view/date context, object details, relationship notes/dates, linked findings and their source/review status, and available supporting screenshots. No external rendering service is used. Word's accompanying text remains editable. Findings excluded from reports also exclude their linked graph objects and relationships; mixed-source objects linked to any excluded finding are omitted conservatively. Missing finding references are labeled unavailable. Milestone history and unfinished browser drafts are not printed. For dense graphs, select a focused saved view to keep the printed figure readable.
