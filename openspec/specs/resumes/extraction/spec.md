# resumes/extraction Specification

## Purpose
Turn a resume file in any supported format into plain text that the parser understands, so the rest of the pipeline never learns which format a file was. Implemented in `plugins/jobkit/src/jk/resumes/extract.py`.

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

### Requirement: PDF text is column-safe and normalized
The system SHALL split a PDF page that has columns (a side bar beside the main column) at the gutter shared by its lines and read the columns one after another, the side bar first and the main column last, so a main column that continues below the columns or on the next page stays in order. The main column is the one with the work-history heading; only when neither or both have it is it the one with more text; full-width text ends a column block. Right-aligned dates, locations and aligned titles without a column SHALL NOT make a gutter; a short block counts as columns when each side has section headings of its own. The system SHALL unfold ligatures (NFKC), turn other list glyphs (dashes, arrows, squares, symbol-font glyphs) into `•`, and remove page numbers, footers repeated on two or more pages and headers repeated from page 1. For such a PDF `text` and `layout_text` SHALL both be the column-by-column text, with list markers normalized again after the columns are split so a right-column dash bullet is a bullet.

#### Scenario: Side bar
- **WHEN** a PDF has skills in a left or right side bar beside the work history
- **THEN** the work history, the skills and the other side-bar sections each parse as their own section

#### Scenario: Side bar with more text than the work column
- **WHEN** a side bar holds more text than the work column beside it and the work continues on the next page
- **THEN** the side bar is read first, and the next page's bullets and employers stay in the work history

### Requirement: Docx structure is flattened to readable lines
The system SHALL read docx files without third-party libraries, keeping paragraphs, line breaks, tabs, table cells, list items (as `•` bullets), content controls and the text of text boxes anchored in body paragraphs, and SHALL ignore headers and footers.

#### Scenario: Table layout
- **WHEN** a resume uses a table with company in one cell and dates in another
- **THEN** the cells of a row are joined on one line separated by a gap, and a two-cell row with a date cell puts the date after the entry

#### Scenario: Page laid out as a table
- **WHEN** some cell of a table with several columns starts with a section heading (`Leadership Skills | Technical Skills`)
- **THEN** the table is read column after column so each heading stays with its list

#### Scenario: Merged heading row
- **WHEN** a table starts with a heading cell (merged, or beside empty cells as in a Markdown pipe table) above timeline rows
- **THEN** the heading stays in place and the rows below are read by their own structure, a timeline row as one line

#### Scenario: Work continues after a table
- **WHEN** a layout table has the work-history heading in one column and other sections in a side column, and more work follows below the table
- **THEN** the side columns are read first and the work column last, so the work below the table continues it

#### Scenario: Numbering switched off in a style
- **WHEN** a style based on a numbered style sets numbering to 0
- **THEN** its paragraphs are not bullets, and neither are paragraphs of styles based on it

#### Scenario: Text box side bar
- **WHEN** a body paragraph anchors a text box (Word writes its text twice)
- **THEN** the text is read once, as its own block with its paragraphs and lists intact

#### Scenario: Bullets set by a paragraph style
- **WHEN** a paragraph's style, or the style it is based on, carries list numbering and the paragraph does not turn it off
- **THEN** the paragraph is a `•` bullet

#### Scenario: Text box in the body
- **WHEN** a body paragraph anchors a text box
- **THEN** the text box's text is part of the extracted lines

### Requirement: Markdown is cleaned to plain lines
The system SHALL convert markdown (including pandoc output: grid tables, pipe tables, spans, autolinks, backslash line breaks, blockquotes) to plain resume lines.

#### Scenario: Pandoc export
- **WHEN** a docx is converted to markdown with pandoc
- **THEN** it parses to the same work history as the original docx

#### Scenario: Markdown layout table
- **WHEN** a grid or pipe table has a cell that starts with a section heading (for example `Leadership | Technical`), also when the heading is bold
- **THEN** the table is read column after column, so each heading stays with its list; any other table is read row by row, with a timeline row (an entry beside its dates) as one line

### Requirement: Contact and address lines are dropped
The system SHALL remove lines that contain only an email, phone, LinkedIn URL or postal address, or several of these separated by `|`, `·` or `•`, from txt, md and docx text, and SHALL drop a table row's short cells when the row holds a contact block. The parser SHALL also skip such lines in the summary, headline and work history of every format, PDF included, so a stray contact line never becomes a headline, summary or bullet text. A line that mixes contact details with other text is kept.

#### Scenario: Address after the last bullet
- **WHEN** the final bullet is followed by a street/city/ZIP line
- **THEN** the address line does not become part of the bullet

### Requirement: Unreadable files do not stop the batch
The system SHALL record an unreadable file in the ledger and in the unparsed list with the error message, and SHALL continue with the remaining files.

#### Scenario: Corrupt docx
- **WHEN** one file in a folder cannot be opened
- **THEN** processing continues and the file is reported as unreadable

#### Scenario: Corrupt PDF
- **WHEN** a PDF is damaged, whether read with poppler or pypdf
- **THEN** it is reported as unreadable with the reader's message and the other files are still processed

### Requirement: Empty extractions name their cause
When extraction yields no usable text, the system SHALL fail that file with a message naming the likely cause, instead of reporting a generic "not a resume". For a PDF with no text layer the message SHALL say it looks like a scanned image and that OCR is not supported. For a docx with no body text but text in a header or footer the message SHALL say the text is in a part that is not read.

#### Scenario: Scanned PDF
- **WHEN** a PDF contains only page images
- **THEN** the file is reported unreadable with a message that it looks scanned and has no text layer

### Requirement: A visual reading can be compared with the parse
The system SHALL print the JSON shape of a visual reading (`process-resumes visual schema`) and SHALL compare a reading in that shape (`visual compare FILE --reading JSON`) with a fresh parse of the same PDF, reporting employers, titles, dates, bullets, skills, certifications, education and summary that only one side has or that differ, each with both versions. It SHALL NOT change any stored data or merge wording. Items are paired by likeness (roles by employer and start date) and then compared exactly, job titles included (digits, decimal points, signs and punctuation such as `C++` count; only case, spacing, typographic quotes and dashes and trailing punctuation do not), and a summary present on one side only is a difference. A reading with a wrong shape SHALL be refused naming the field. A transcript confirmed for the PDF SHALL be used in place of the PDF text, whether the parser could read the PDF or not.

#### Scenario: Parser missed a bullet
- **WHEN** the visual reading has a bullet the parse lacks
- **THEN** the report lists it as missing from the parser, with the visual text

#### Scenario: Close but different
- **WHEN** the readings differ only by `BS` and `MS`, `C` and `C++`, `1.5` and `15`, or `Associate` and `Professional`
- **THEN** each is reported as a difference with both versions

#### Scenario: Correction that loses work bullets
- **WHEN** a transcript for a PDF the parser could read drops a role or a work bullet of the PDF's own text (roles paired by employer and start date, bullets within a role by likeness, so a bullet moved to another employer counts even when the totals agree, and a reworded bullet does not)
- **THEN** `visual confirm` refuses it, lists each dropped role and bullet, and points to `visual text FILE --layout`

#### Scenario: Agreed removal
- **WHEN** the user agreed to remove an erroneous role or bullet and `visual confirm FILE --remove TEXT` names each dropped item as listed
- **THEN** the transcript is confirmed and the removed items are recorded beside it; a `--remove` that names no dropped item is refused

#### Scenario: Corrected reading
- **WHEN** the agreed text is saved and confirmed for a PDF the parser could read
- **THEN** the next run parses that text instead of the PDF text, until the PDF changes

### Requirement: A PDF the parser cannot read may be read visually, once the user responds with yes
The system SHALL mark a PDF with no text layer, or one that cannot be opened as a PDF, as needing a visual reading (and no other failure, such as a Word file or a PDF that parsed but is not a resume), say so in its message, `--survey` and the unparsed report, and SHALL NOT read it visually by itself. `process-resumes visual list` SHALL list such files with the PDF path and the path for the transcript under `output/visual/` in the home folder. A transcript SHALL be used in place of the PDF text only after `process-resumes visual confirm FILE`, which ties it to the checksum of the PDF as it is then; editing a transcript SHALL NOT change which PDF it is tied to, and after the PDF is replaced the old transcript SHALL NOT be used until a new one is confirmed. The ledger SHALL record the transcript checksum and its state, so a transcript that becomes confirmed is read even when its text is unchanged. Each source path SHALL have its own transcript name, and the resume folder SHALL never be written. For an agent that cannot open a PDF's pages itself, `process-resumes visual render FILE` SHALL write the pages as images under `output/visual/pages/` in the home folder and print their paths, drawing them with `pdftoppm` when installed and otherwise copying out the embedded JPEG only of a plain scan (each page's parsed content draws one unmasked JPEG in gray or RGB over the whole page and nothing else: no text, tiles, clip, vector painting, graphics state, annotations, crop box or rotation), and SHALL say how to install poppler when neither works; a PDF of more than 30 pages SHALL be refused with a message, never cut short; confirming the transcript SHALL remove those images.

#### Scenario: Scan found
- **WHEN** a PDF has no text layer
- **THEN** the report names it as needing a visual reading, the command reads nothing visually, and the skill tells the agent to ask first and read the pages only once the user responds with yes

#### Scenario: Transcript saved
- **WHEN** a transcript exists for such a PDF
- **THEN** the next run parses the transcript as that file's text and a later change to the transcript reprocesses the file

#### Scenario: Pages as images
- **WHEN** the agent cannot open a PDF's pages and runs `visual render` for a scanned PDF
- **THEN** one image per page is written under `output/visual/pages/`, their paths are printed, and they are removed when the transcript is confirmed

#### Scenario: A page that is not a plain scan
- **WHEN** poppler is not installed and a page holds several image tiles, any text, a clip, vector painting over the image, annotations, a rotation, or an image that does not exactly cover the page
- **THEN** the command fails with the poppler advice and returns no part of a page

#### Scenario: A long PDF
- **WHEN** a PDF has more than 30 pages
- **THEN** the command fails naming the limit and writes no images

#### Scenario: No way to draw the pages
- **WHEN** poppler is not installed and the PDF has no embedded JPEG page images
- **THEN** the command fails with a message that says how to install poppler and writes no images

#### Scenario: Other failures
- **WHEN** a docx cannot be opened
- **THEN** it is reported unreadable and no visual reading is offered

#### Scenario: Docx with text only in a header
- **WHEN** a docx body has no text but its header holds the content
- **THEN** the file is reported unreadable with a message that its text is in a header or footer, which is not read

#### Scenario: Truly empty file
- **WHEN** a text file is empty
- **THEN** the message says the file has no text

#### Scenario: Batch continues
- **WHEN** one file fails this way
- **THEN** the remaining files are still processed and the file appears in the unparsed list with its message
