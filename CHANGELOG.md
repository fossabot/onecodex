# Changelog

## [v0.8.0] - 2020-06-02

### Added

-   Adds more pythonic support for truthy/falsey values to SampleCollection.filter()
-   Adds support for passing lists to the various sort_x and sort_y plotting arguments
-   Adds a property to SampleCollection to track whether we think the collection is all WGS/metagenomic data
-   Adds support for specifying weighted_unifrac and unweighted_unifrac as metrics in the SampleCollection.beta_diversity() method
-   Adds support for calculating alpha and beta diversities on normalized data. This is important since we'll now be using abundances by default for most datasets
-   Adds support for specifying chart width and height directly in the plot\_\* functions
-   Adds option to plot "Other" bars on bargraphs with normalized read counts and abundances
-   Adds option to plot "No \<level\>" bars on bargraphs with abundances
-   Adds abundance rollups so we can use abundances at all taxonomic ranks
-   Adds a project column to the metadata DataFrame of a SampleCollection

### Changed

-   Changes default alpha diversity metric from simpson to shannon, since shannon is generally a more appropriate default
-   rank="auto" now defaults to species if the field="abundances" or the dataset is metagenomic, instead of genus
-   Switches to using a normalized tree for Weighted Unifrac calculations, which gives us Unifrac values in a [0, 1] range
-   Defaults to using abundances data for metagenomic datasets instead of readcount_w_children

### Deprecated

-   The `field` kwarg on the `SampleCollection` constructor has been renamed to `metric`. We still support passing either, but show a `DeprecationWarning` when passing `field`

### Removed

-   Removes support for just specifying `unifrac` as a metric