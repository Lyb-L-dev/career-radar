---
name: Career Radar
description: A restrained career operating tool that makes job requirements and capability evidence traceable.
colors:
  background: "hsl(240 11% 96%)"
  primary: "hsl(218 89% 41%)"
  growth-primary: "hsl(218 89% 41%)"
  primary-foreground: "hsl(0 0% 100%)"
  brand-mark: "#1677FF"
  brand: "#0B4FC4"
  brand-foreground: "#0B4FC4"
  brand-soft: "#EAF3FF"
  surface: "#FFFFFF"
  surface-subtle: "#FAFAFA"
  ink: "#1D1D1F"
  ink-body: "#333336"
  ink-secondary: "#6E6E73"
  ink-tertiary: "#6E6E73"
  border: "hsl(240 6% 91%)"
  input-border: "hsl(240 2% 56%)"
  success: "#137A4F"
  warning: "#92400E"
  danger: "#B42318"
  destructive: "hsl(4 74% 49%)"
typography:
  headline:
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif'
    fontSize: "28px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.025em"
  title:
    fontSize: "20px"
    fontWeight: 600
    lineHeight: "28px"
  title-small:
    fontSize: "18px"
    fontWeight: 600
    lineHeight: "28px"
  body:
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.75
  ui:
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontSize: "14px"
    fontWeight: 500
    lineHeight: "20px"
  supporting:
    fontSize: "12px"
    fontWeight: 400
    lineHeight: "16px"
rounded:
  md: "8px"
  lg: "10px"
  xl: "12px"
spacing:
  2: "8px"
  3: "12px"
  4: "16px"
  5: "20px"
  6: "24px"
components:
  button-primary-growth:
    backgroundColor: "{colors.growth-primary}"
    textColor: "{colors.primary-foreground}"
    rounded: "{rounded.md}"
    height: "36px"
    padding: "8px 16px"
    typography: "{typography.label}"
  button-outline:
    backgroundColor: "{colors.background}"
    rounded: "{rounded.md}"
    height: "36px"
    padding: "8px 16px"
    typography: "{typography.label}"
  button-ghost:
    rounded: "{rounded.md}"
    height: "36px"
    padding: "8px 16px"
    typography: "{typography.label}"
  input:
    rounded: "{rounded.md}"
    height: "36px"
    padding: "4px 12px"
  textarea:
    rounded: "{rounded.md}"
    padding: "8px 12px"
  navigation-selected:
    backgroundColor: "{colors.brand-soft}"
    textColor: "{colors.brand-foreground}"
    rounded: "{rounded.lg}"
    height: "44px"
    padding: "0 12px"
    typography: "{typography.label}"
  growth-card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.xl}"
    padding: "20px"
  skill-node-selected:
    backgroundColor: "{colors.brand-soft}"
    textColor: "{colors.ink-body}"
    rounded: "{rounded.xl}"
    width: "144px"
    padding: "12px"
---

# Design System: Career Radar

## Overview

**Creative North Star: "Traceable capability evidence"**

Career Radar is a quiet, practical operating tool. Light neutral surfaces, white containers, Chinese system typography, restrained blue actions, and Lucide line icons continue the existing product world. The growth extension makes the relationship between a selected job requirement, a skill, its evidence, and the next action visible.

This record merges the inspected shared shell, home opportunity summary, and growth extension into the incumbent system. It does not replace `web/DESIGN_SPEC.md` or claim that uninspected screens follow every component pattern below. Source values and sampled components are the authority; the growth heading and shared controls reflect their built sizes rather than the older specification's proposed sizes. The current frontend work changes presentation and navigation; backend scoring remains unchanged.

**Key Characteristics:**

- Neutral surfaces organize information; blue identifies action and selection.
- Chinese text remains readable at daily operating density.
- Skill states and evidence provenance are explicit in words.
- A geometric prerequisite map supports inspection rather than decoration.

## Colors

White and light neutral surfaces carry the content; a single blue family carries actions and selection, with semantic color reserved for status.

### Primary

- **Career Blue Mark** (`brand-mark`): the incumbent brand mark accent, reserved for the mark rather than reading text or filled actions.
- **Readable Action Blue** (`primary`, `growth-primary`): the shared semantic primary for white button labels; the growth scope repeats the same source value. Preserve the source HSL format.
- **Readable Link Blue** (`brand`, `brand-foreground`): links, selected view labels, next-action text, and selected-node borders. Preserve the source hex format.
- **Soft Blue** (`brand-soft`): selected navigation, selected skill nodes, and teaching context.

### Neutral

- **Page Neutral** (`background`): shared page background and outline-button fill.
- **White Surface** (`surface`, `primary-foreground`): content containers and primary-button labels, respectively.
- **Subtle Surface** (`surface-subtle`): quoted answers, code blocks, and nested requirement containers.
- **Heading Ink**, **Body Ink**, and **Supporting Ink** (`ink`, `ink-body`, `ink-secondary`, `ink-tertiary`): titles, primary reading, and explanatory metadata. Tertiary copy now shares the readable supporting ink rather than a lighter gray.
- **Control Border** (`border`): shared outline-control boundary and container dividers.
- **Input Boundary** (`input-border`): the stronger shared input and textarea boundary; separate from container dividers.

Success green, warning amber, and danger red indicate meaningful outcomes and uncertainty in the inspected shell and home summary. Danger is the darker status-text token; destructive remains the separate CSS semantic token for destructive controls and their white labels. Growth also retains local amber utility shades for review due, partial evidence, and recoverable failures; those local variations are not new brand accents.

**The Action Contrast Rule.** Text actions use Readable Link Blue; shared filled primary actions use Readable Action Blue with white labels. Career Blue Mark remains a brand-mark accent.

## Typography

**Body Font:** the system stack recorded in `headline.fontFamily`, inherited by headings, labels, and prose. Chinese fallbacks are PingFang SC and Microsoft YaHei. The extension is an operating interface with no separate display face.

### Hierarchy

- **Headline:** inspected home and growth page titles; compact semibold with tight tracking where applied. Shared PageHeader renders 28px below 768px and 32px from that breakpoint; home and growth retain their local 28px headings.
- **Title:** task, skill-detail, and session titles.
- **Title small:** secondary module headings and job titles.
- **Body:** long JD reading, expanded opportunity explanations, evidence, and answered-session teaching use the shared reading treatment, capped at 48rem, with wrapping. Short requirement quotes and the initial hint block retain their local typography; the reading role is not applied to every paragraph.
- **UI:** inherited operating text, list rows, and compact descriptions. Growth explanatory blocks also use explicit line heights of 24px or 28px where present.
- **Label:** shared buttons and view navigation.
- **Supporting:** provenance, dates, rubric versions, and secondary state. Multi-line supporting copy uses a 20px line height where present.

Code and submitted run records use the utility monospace stack within readable, scrollable text blocks; it is not a brand font.

**The Title First Rule.** Full daily task cards put the task heading before its learning/project category. Category text is subordinate task metadata, not an eyebrow style for new surfaces.

## Layout

The inspected shell has a fixed white 224px sidebar from 768px and a 256px navigation sheet below it. The top bar is sticky and 64px high. Main content is centered with a maximum width of 1440px, 16px horizontal and 24px vertical padding on phones, increasing to 32px from 768px. A keyboard-visible skip link targets the main region. Search opens a command palette through its named button or Ctrl/Command+K.

The current home summary reads in order: job overview, two source-specific opportunity groups, the growth summary with two daily tasks, pending items, then monitoring. Each source group shows at most three opportunities; enterprise recruitment pages and BOSS platform leads have separate source labels, qualification wording, and full-list links. The pair forms two columns from 1024px and stacks below. Monitoring statistics and scan actions follow saved opportunities. This is the home composition, not a mandatory hierarchy for every page.

Growth sections use a vertical rhythm of 24px, with 20px or 24px grid gaps and 20px default card padding. Larger daily-task cards increase to 24px padding from the medium breakpoint; sessions increase to 28px. These are observed component variations, not a mandatory padding for every screen.

The default `/growth` view remains the fixed prerequisite roadmap. After heading and view navigation, an applicable next-step or resume prompt and the two-action summary precede target-sample context, map, and selected evidence. At the extra-large breakpoint (1280px), selection creates a flexible map column plus a 360px evidence column. From 768px to 1279px, both remain visible in a stacked grid. Below 768px, selected detail replaces the map; closing detail restores a grouped skill list with textual prerequisites. Do not shrink the desktop graph into a phone diagram.

The desktop prerequisite map uses fixed columns by dependency depth and rows within each depth: origin (20px, 20px), column pitch (164px), and row pitch (132px). Nodes are 144px wide with a minimum height of 108px. The graph canvas scrolls horizontally, is keyboard focusable, and sizes to its content. Curved procedural SVG arrows connect prerequisite nodes; they are information geometry, not decorative image assets.

Daily actions form two columns from 1024px and a single column below. Text and submitted materials wrap; long code and graph content scroll within their own container.

## Elevation & Depth

The inspected growth containers are flat. White and subtle fills, spacing, occasional dividing rules, and selected-node borders express structure. Shared theme shadows remain incumbent tokens, but the growth extension does not apply them to every card.

### Shadow Vocabulary

- **Card:** `0 1px 2px rgba(0,0,0,0.03), 0 8px 24px rgba(0,0,0,0.04)`; an incumbent theme option, not a default for these growth containers.
- **Pop:** `0 4px 16px rgba(0,0,0,0.08), 0 16px 48px rgba(0,0,0,0.08)`; an incumbent theme option whose use on other surfaces was not inspected.

Focus feedback is distinct from elevation: shared controls use a 3px half-opacity semantic ring; desktop graph nodes use a 2px readable-blue outline offset by 2px. Global keyboard focus uses a 2px readable-blue outline offset by 3px. Reduced-motion preference suppresses animation and transition duration and restores automatic scroll behavior.

## Shapes

The growth extension combines gently rounded rectangular cards and precise geometric graph nodes. Card/node corners use the `xl` radius. Shared Button, Input, and Textarea use the `md` radius; the built value is 8px even though the older design specification proposed 10px controls. View navigation and inline selects use the `lg` radius. Borders support controls, graph connections, and selection instead of boxing every piece of prose.

## Components

### Buttons

Compact, textual actions with optional Lucide icons. Default shared buttons are 36px high, medium-weight 14px text, an 8px radius, and 8px by 16px padding; an immediate icon child reduces horizontal padding to 12px. Small buttons are 32px high. Icon-only utility buttons have an accessible name.

Shared and growth primary buttons use the readable semantic primary; hover uses the same primary at 90% opacity. Outline actions use the shared page background and control border, becoming accent-filled on hover. Ghost actions gain an accent fill and accent foreground on hover. Shared focus rings remain visible, and disabled buttons reduce opacity to 50% and stop pointer interaction. Busy states use explicit action labels and disabled controls rather than suggesting successful completion. Below 768px, buttons and button-role controls have a global minimum height of 44px; native disclosure summaries also increase to 44px.

### Cards / Containers

White, flat, 12px-corner containers group opportunities, a task, selected evidence, a session, or job comparison. Default internal padding is 20px; shared Card increases to 24px from 768px. Nested quoted material uses the subtle surface and 10px corners. Division between records uses light neutral rules rather than a stack of elevated cards.

### Inputs / Fields

Visible labels identify text inputs and multi-line answers. Shared fields are transparent with a semantic input border and 8px corners. Input height is 36px; Textarea minimum height is 64px. Text is 16px below 768px and 14px from that breakpoint. Focus changes the border to the ring color and adds the 3px half-opacity ring. Invalid state uses destructive border/ring; disabled fields reduce opacity and indicate inactivity. The user must be able to distinguish answer, code/material, explanation, and user-submitted run record.

### Navigation

Growth view navigation wraps naturally rather than clipping. View buttons have a minimum height of 44px, 12px horizontal padding, and a 10px radius. The selected view uses Soft Blue and Readable Link Blue; unselected text uses Supporting Ink and a light neutral hover fill. Current-view semantics are explicit. The inspected global shell provides named navigation, search, notification, and user-menu controls; this does not establish consistency for every destination screen.

Jobs source/filter selection and growth view, skill, target, session, and evidence selection use URL state where implemented, so browser navigation can recover context. Job-detail `from` accepts only an internal `/jobs` path and its query; other values fall back to `/jobs`. Growth answer, task-reflection, and project-material drafts are stored locally where implemented. Local draft persistence is a reading/editing aid, not capability evidence.

### Prerequisite map

Each graph node is a real button with a pressed state and a descriptive accessible label. Neutral nodes are white with a light border; recommended nodes use a blue-tinted border; selected nodes use Soft Blue and a solid brand border. Hover and keyboard focus identify the interactive node. Status, level, due review, and recommendation have text alongside line icons. No level is shown for an unverified skill.

### Evidence and recall

Evidence panels use ordinary headings, definitions, lists, and disclosure elements. The first three evidence records appear by default, with an explicit control for all records. A selected evidence URL or anchor reveals and focuses the referenced record, including records beyond the initial three. Panels keep self-report, independent recall, assisted practice, project material/code review, implementation follow-up, and user-submitted run records visibly distinct. Job requirement links retain the quoted JD text and return to the relevant target. Recall answers and feedback wrap; source code scrolls. A skipped answer stays unscored, and assistance is labeled. Review due indicates a recall need, not automatic capability loss over time. These presentation changes do not alter backend scoring.

**The Evidence Before Claim Rule.** A capability statement must lead back to its recorded evidence; a learning action must lead back to a selected job requirement. Unknown capability stays explicitly unverified.

### Dialogs and feedback

The shared dialog close control has a 36px hit area from 768px and a 44px area below, with a screen-reader label. The application mounts the shared top-center toast component, whose success, warning, information, and error text follow the readable status/action colors above. Loading, saved, retry, and failed states retain explicit text rather than relying on color alone. This describes inspected component source, not a completed accessibility audit of every screen.

## Do's and Don'ts

### Do:

- **Do** continue the incumbent light neutral, white, blue, Chinese system-sans, and Lucide visual world.
- **Do** use Readable Link Blue for text actions and the readable semantic primary for filled actions; reserve Career Blue Mark for the brand mark.
- **Do** use the long-reading role for JD, expanded evidence, and teaching where implemented, preserving compact UI typography for operating controls.
- **Do** preserve requirement quotes, evidence provenance, and an explicit unknown state.
- **Do** keep daily-task category metadata beneath the heading.
- **Do** use the grouped mobile list and selected-detail replacement behavior for the growth map.

### Don't:

- **Don't** use learning hours, budget minutes, or manually completed tasks as capability progress.
- **Don't** imply that reviewing a user-submitted run record means the application executed the code.
- **Don't** treat temporary QA fixture screenshots as real user capability evidence.
- **Don't** introduce a new visual identity, decorative raster imagery, saturated multicolor page treatment, or a dark blue sidebar for this extension.
- **Don't** generalize local graph geometry or uninspected page behavior into a rule for every product surface.
