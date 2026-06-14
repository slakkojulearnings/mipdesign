# Generate Daily Batch Processing Workflow

Using only JCL, scheduler, dataset producer/consumer, and validated relationship evidence:

- identify batch roots
- order jobs by explicit scheduling and data dependencies
- show each job's major steps and executed programs
- show important input and output datasets
- trace data from initial input through processing to final output
- mark unresolved ordering or missing jobs
- generate overview and detailed Mermaid diagrams
- cite source evidence in the accompanying Markdown

Do not infer runtime order from file names alone.
