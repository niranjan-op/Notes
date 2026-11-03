# AGENTS.md

# Secure Notes - Project Engineering Guidelines

## 1. Project Overview

Secure Notes is a local-first, encrypted desktop note-taking and knowledge-management application.

Its primary purpose is to provide users with a secure environment for creating, organizing, editing and connecting Markdown notes.

The application should prioritize:

- Security and privacy.
    
- Reliability and data integrity.
    
- A polished desktop user experience.
    
- Simple and intuitive note organization.
    
- Maintainable, modular architecture.
    
- Fast and responsive interactions.
    

This is a desktop application, not a web application.

## 2. Technology Stack

The existing application uses:

- Python
    
- CustomTkinter for the desktop UI.
    
- Tkinter for underlying GUI functionality.
    
- An encrypted native storage extension (`secure_storage`).
    
- A custom Vault abstraction.
    
- PyInstaller for executable packaging.
    

Use the existing technology stack unless a change is explicitly requested and technically justified.

Do not introduce React, Next.js, Electron, browser-based interfaces or unrelated frameworks.

Before introducing a new dependency, evaluate whether the existing stack can solve the problem.

Avoid unnecessary dependencies and excessive abstraction.

## 3. Architecture and Code Organization

Follow the existing project architecture.

Important locations include:

- `main.py`: Application entry point.
    
- `app/UI/`: User interface components and views.
    
- `app/core/`: Core application logic and vault functionality.
    
- `app/UI/styles.py`: Shared visual styling and theme definitions.
    
- `app/core/vault.py`: Vault abstraction.
    
- `app/core/config.py`: Application configuration.
    

Inspect existing modules before modifying them.

Architectural principles:

1. Separate UI rendering from business logic.
    
2. Keep storage operations outside presentation components wherever practical.
    
3. Use reusable components instead of duplicating UI code.
    
4. Keep application state explicit and predictable.
    
5. Avoid circular imports.
    
6. Avoid excessively large classes and modules.
    
7. Use clear names for classes, functions and variables.
    
8. Keep functions focused on a single responsibility.
    
9. Avoid unnecessary global state.
    
10. Prefer composition over deeply nested inheritance.
    

Do not reorganize the entire project merely for stylistic reasons.

When modifying an existing module, preserve its established responsibilities unless there is a clear architectural reason to change them.

## 4. Security and Data Integrity

Security is a fundamental application requirement, not an optional feature.

Never compromise the existing encryption or authentication implementation for UI convenience.

Rules:

- Never store vault passwords in plaintext.
    
- Never log passwords, encryption keys or sensitive note contents.
    
- Never bypass authentication to simplify navigation.
    
- Never expose data from a locked vault.
    
- Never weaken encryption settings without explicit authorization.
    
- Clear sensitive in-memory references when locking a vault.
    
- Handle database connections and resources safely.
    
- Ensure destructive operations require appropriate confirmation.
    
- Never silently discard unsaved changes.
    

Maintain compatibility with existing vaults.

Do not change the storage format, encryption mechanism, database schema or cryptographic implementation without first understanding the consequences.

When a storage migration is unavoidable:

1. Explain the reason.
    
2. Preserve existing data.
    
3. Provide a backward-compatible migration where possible.
    
4. Test the migration using existing vault data.
    

## 5. UI/UX Design Principles

The application should have a coherent, premium desktop design.

Design direction:

- Modern.
    
- Minimal.
    
- Elegant.
    
- Productivity-oriented.
    
- Content-focused.
    
- Consistent.
    

Take inspiration from applications such as Obsidian, Craft and Linear without copying their interfaces.

### Design rules

- Maintain a centralized design system.
    
- Use consistent spacing, typography, colours, borders and corner radii.
    
- Prefer subtle borders and restrained visual emphasis.
    
- Use a consistent icon library or icon system.
    
- Avoid emoji and arbitrary Unicode symbols as UI icons.
    
- Avoid excessive gradients, shadows and decorative elements.
    
- Avoid unnecessarily large buttons and controls.
    
- Avoid excessive rounded cards.
    
- Maintain clear visual hierarchy.
    
- Ensure sufficient colour contrast.
    
- Provide clear hover, active, selected, disabled and focus states.
    

### Theme management

Support the application's existing dark and light themes.

All shared UI components should use centralized theme tokens.

Do not hardcode colours independently across multiple components.

Switching themes should update all relevant parts of the interface consistently.

### Component consistency

Buttons, inputs, menus, dialogs, tooltips and other reusable elements must follow shared styling conventions.

Do not implement a second visual style for an existing component type without a clear reason.

## 6. Desktop Interaction Guidelines

Design interactions specifically for a desktop application.

Prefer:

- Context menus for note and folder actions.
    
- Keyboard shortcuts for frequent operations.
    
- Drag-and-drop for intuitive note organization.
    
- Custom in-app dialogs for application workflows.
    
- Tooltips for unfamiliar controls.
    
- Inline validation where appropriate.
    
- Clear feedback after operations.
    

Avoid default Tkinter message boxes and dialogs for routine application interactions.

Use native operating-system file dialogs when appropriate, such as importing or exporting files.

All interactions must perform real operations.

Never implement decorative controls that appear functional but do nothing.

## 7. Window Management and Responsiveness

The application must work across different desktop resolutions and Windows display-scaling settings.

Requirements:

- Use sensible initial window dimensions.
    
- Maintain appropriate minimum dimensions.
    
- Prevent clipped or inaccessible controls.
    
- Handle resizing gracefully.
    
- Preserve the usability of navigation, editor and contextual panels.
    
- Avoid hardcoded absolute positioning wherever possible.
    
- Prefer responsive layouts and appropriate geometry management.
    
- Account for different DPI scaling settings.
    

Do not assume that every user has the same monitor resolution.

Test the application at multiple window sizes.

## 8. State Management and Persistence

Application state must remain consistent across UI interactions.

Rules:

- Avoid unnecessary application-wide state.
    
- Keep selected vault, note and folder state predictable.
    
- Persist changes reliably.
    
- Avoid duplicate save operations where they can cause problems.
    
- Handle autosave callbacks and scheduled operations safely.
    
- Cancel outstanding callbacks when their associated views or vaults are destroyed.
    
- Prevent race conditions involving navigation and saving.
    
- Preserve the selected note when performing folder operations where appropriate.
    

Never assume that a UI update means the underlying data was successfully persisted.

Handle storage errors explicitly and provide useful feedback.

## 9. Error Handling and Logging

Use meaningful exception handling.

Avoid broad `except Exception` blocks that silently suppress errors.

When handling an error:

1. Identify the actual failure.
    
2. Preserve application and vault integrity.
    
3. Log useful diagnostic information without sensitive data.
    
4. Show an understandable message to the user when appropriate.
    

Avoid exposing raw tracebacks or internal implementation details in normal user-facing error messages.

Use structured and consistent logging where practical.

## 10. Python Coding Standards

Follow modern Python conventions.

- Use type hints for function signatures.
    
- Prefer descriptive names.
    
- Keep functions and methods reasonably small.
    
- Add docstrings to important public classes and functions.
    
- Avoid unnecessary comments that simply restate the code.
    
- Use pathlib for filesystem operations where appropriate.
    
- Use context managers for resource management.
    
- Avoid mutable default arguments.
    
- Use constants for repeated configuration values.
    
- Avoid unnecessary dependencies and complicated design patterns.
    

Follow PEP 8 where practical.

Do not introduce unnecessary abstractions simply to make code appear more sophisticated.

## 11. Testing Requirements

Test existing functionality after making changes.

Important functionality includes:

- Vault creation.
    
- Vault selection.
    
- Authentication.
    
- Vault locking.
    
- Note creation and deletion.
    
- Note editing and persistence.
    
- Folder creation and management.
    
- Moving notes between folders.
    
- Markdown import.
    
- Backlinks.
    
- Graph view.
    
- Theme switching.
    
- Window resizing.
    
- Autosave and navigation.
    

Add regression tests when modifying core functionality.

For storage changes, test the actual storage behaviour rather than relying exclusively on mocked UI interactions.

Do not claim something is working merely because the application starts successfully.

## 12. Git and Build Artifacts

Keep source code separate from generated artifacts.

Do not modify or commit generated files unless explicitly necessary.

Pay attention to:

- `dist/`
    
- `build/`
    
- `__pycache__/`
    
- `.venv/`
    
- Generated executables.
    
- Temporary files.
    
- Local configuration and secret files.
    

Follow the repository's existing `.gitignore`.

Never overwrite user data, vault databases or existing backups during development or testing.

## 13. Working With Codex

Before modifying code:

1. Inspect the relevant source files.
    
2. Understand the existing implementation.
    
3. Identify dependencies and side effects.
    
4. Determine which existing functionality must be preserved.
    
5. Plan the smallest maintainable implementation.
    

During implementation:

- Prefer targeted changes.
    
- Reuse existing functionality.
    
- Avoid unnecessary rewrites.
    
- Keep related changes logically organized.
    
- Do not invent APIs or assume methods exist without inspecting the implementation.
    

After implementation:

1. Run relevant tests.
    
2. Check for regressions.
    
3. Inspect the actual UI where applicable.
    
4. Check error handling and edge cases.
    
5. Summarize changed files and important decisions.
    
6. Explicitly mention anything that remains incomplete.
    

Do not report tests as passing unless they were actually executed.

## 14. Definition of Done

A change is complete only when:

- The requested functionality works.
    
- Existing functionality remains intact.
    
- Data integrity and security are preserved.
    
- The code follows the existing architecture.
    
- The UI follows the centralized design system.
    
- Relevant tests pass.
    
- Errors are handled appropriately.
    
- The implementation has been checked for edge cases.
    

The objective is not merely to make the application functional.

The objective is to build a secure, reliable and thoughtfully designed desktop application that is pleasant to use and straightforward to maintain.