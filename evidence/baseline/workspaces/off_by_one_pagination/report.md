When I ask for the first page of results I don't get the first few items -- it looks
like it's skipping ahead somehow. A 10-item list with a page size of 3: page 1 gives me
items 4, 5, 6 instead of 1, 2, 3. Page 2 looks off too. Not sure if this is in the
pagination helper or somewhere upstream in how we're slicing the data.
