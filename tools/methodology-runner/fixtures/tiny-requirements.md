# LOC Counter — Requirements

A small command-line tool that reports lines of code in a directory tree,
grouped by file extension.

## Context and motivation

Developers often want a quick overview of the size of a codebase or a
specific subdirectory. Existing tools like `cloc` or `tokei` are powerful
but have many options and a heavy runtime. This tool is intentionally
minimal: single binary, zero configuration, sensible defaults.

## Requirements

### Functional

1. The tool shall accept one or more directory paths as positional
   command-line arguments.
2. The tool shall recursively walk each given directory, reading every
   text file under it.
3. The tool shall count the number of newline-terminated lines in each
   file.
4. The tool shall group files by their extension (for example, `.py`,
   `.ts`, `.md`) and report the total line count per extension.
5. The tool shall print a summary table with columns: extension, file
   count, total lines, sorted by total lines descending.
6. The tool shall exit with status 0 on success and non-zero on error.

### Non-functional

7. The tool shall run on Python 3.11 or later.
8. The tool shall complete in under 2 seconds for directory trees
   containing up to 10,000 files on a modern laptop.
9. The tool shall use only the Python standard library (no third-party
   dependencies).

### Constraints

10. The tool shall skip directories whose names match common ignore
    patterns: `.git`, `node_modules`, `__pycache__`, `.venv`, `venv`,
    `build`, `dist`.
11. The tool shall skip files larger than 10 MB (binary files and large
    data dumps are not the tool's concern).
12. The tool shall not follow symbolic links.

### Assumptions

13. Users will run the tool against source code repositories, not
    arbitrary file systems.
14. Files whose content cannot be decoded as UTF-8 are treated as binary
    and are skipped.
