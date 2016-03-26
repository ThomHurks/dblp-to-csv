# dblp-to-csv
Convert a DBLP (Computer Science Bibliography) XML file to CSV format.

## Usage
For each element in the XML file, so article, book, phdthesis, etc, this tool will generate an output file.
Each element output file contains only the necessary columns for that element, meaning each column will be non-empty on at least one row.
When multiple similar attribute tags are encountered on an element, e.g. multiple authors of an article, then those values will be contained within an array "[item1|item2|...|itemN]".
When calling the tool, pass as parameters the input XML file, the DTD file and the desired output file name format; e.g. output.csv will generate output_article.csv, output_book.csv, etc.

## Optional type annotated headers
Optionally, one can use --annotate to enable type annotation. Per element, this will create an extra header file containing a single line with an annotated header. This annotated header is of the format name:type per column or name:type[] for columns that contain at least one array entry. The type can be integer, float, boolean or string.

## Links
To learn more about DBLP: http://dblp.dagstuhl.de
