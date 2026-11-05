# resumes/extraction Specification

## Purpose
Turn a resume file in any supported format into plain text that the parser understands, so the rest of the pipeline never learns which format a file was. Implemented in `src/jobkit/resumes/extract.py`.

## Requirements

### Requirement: One entry point returns a uniform document
The system SHALL expose `extract(path)` that returns an `ExtractedDocument` with `text`, `layout_text` and `format`, regardless of the file's format.

#### Scenario: Same resume in different formats
- **WHEN** one resume is saved as txt, md and docx
- **THEN** each file extracts to text that parses into the same companies and bullets

### Requirement: Formats are selected by suffix through a registry
The system SHALL support `.pdf`, `.docx`, `.md`, `.markdown` and `.txt`, choosing the extractor by file suffix, and a new format SHALL need only one new class registered with `@register`.

#### Scenario: Supported suffixes
- **WHEN** the supported suffixes are listed
- **THEN** they are exactly `.docx`, `.markdown`, `.md`, `.pdf`, `.txt`

#### Scenario: Unsupported legacy format
- **WHEN** a `.doc`, `.rtf` or `.odt` file is given
- **THEN** the system reports a clear error naming the supported suffixes and does not guess

### Requirement: Non-resume files are skipped when scanning
The system SHALL ignore hidden files and Office lock files (names starting with `~$`) when listing resume files.

#### Scenario: Lock file next to a resume
- **WHEN** a folder holds `resume.docx` and `~$resume.docx`
- **THEN** only `resume.docx` is listed

### Requirement: Layout text keeps right-aligned dates separable
The system SHALL provide `layout_text` in which a date range is separated from its heading by at least two spaces. For txt, md and docx, `layout_text` SHALL equal `text`; for PDF it SHALL come from `pdftotext -layout`, falling back to `pypdf`.

#### Scenario: Tab-aligned dates in a docx
- **WHEN** a paragraph is `Company<tab>01/2020 - Present`
- **THEN** the extracted line has a gap of three spaces before the date range

### Requirement: Docx structure is flattened to readable lines
The system SHALL read docx files without third-party libraries, keeping paragraphs, line breaks, tabs, table cells, list items (as `•` bullets), content controls and the text of text boxes anchored in body paragraphs, and SHALL ignore headers and footers.

#### Scenario: Table layout
- **WHEN** a resume uses a table with company in one cell and dates in another
- **THEN** the cells of a row are joined on one line separated by a gap

#### Scenario: Text box in the body
- **WHEN** a body paragraph anchors a text box
- **THEN** the text box's text is part of the extracted lines

### Requirement: Markdown is cleaned to plain lines
The system SHALL convert markdown (including pandoc output: grid tables, pipe tables, spans, autolinks, backslash line breaks, blockquotes) to plain resume lines.

#### Scenario: Pandoc export
- **WHEN** a docx is converted to markdown with pandoc
- **THEN** it parses to the same work history as the original docx

### Requirement: Contact and address lines are dropped from non-PDF text
The system SHALL remove lines that contain only an email, phone, LinkedIn URL or postal address from txt, md and docx text, and SHALL drop a table row's short cells when the row holds a contact block.

#### Scenario: Address after the last bullet
- **WHEN** the final bullet is followed by a street/city/ZIP line
- **THEN** the address line does not become part of the bullet

### Requirement: Unreadable files do not stop the batch
The system SHALL record an unreadable file in the ledger and in the unparsed list with the error message, and SHALL continue with the remaining files.

#### Scenario: Corrupt docx
- **WHEN** one file in a folder cannot be opened
- **THEN** processing continues and the file is reported as unreadable

### Requirement: Empty extractions name their cause
When extraction yields no usable text, the system SHALL fail that file with a message naming the likely cause, instead of reporting a generic "not a resume". For a PDF with no text layer the message SHALL say it looks like a scanned image and that OCR is not supported. For a docx with no body text but text in a header or footer the message SHALL say the text is in a part that is not read.

#### Scenario: Scanned PDF
- **WHEN** a PDF contains only page images
- **THEN** the file is reported unreadable with a message that it looks scanned and has no text layer

#### Scenario: Docx with text only in a header
- **WHEN** a docx body has no text but its header holds the content
- **THEN** the file is reported unreadable with a message that its text is in a header or footer, which is not read

#### Scenario: Truly empty file
- **WHEN** a text file is empty
- **THEN** the message says the file has no text

#### Scenario: Batch continues
- **WHEN** one file fails this way
- **THEN** the remaining files are still processed and the file appears in the unparsed list with its message
