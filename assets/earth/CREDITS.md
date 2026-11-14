# Earth imagery

From NASA's Earth Observatory, Blue Marble Next Generation
(https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/),
downloaded 2026-11-14 with the user's approval from assets.science.nasa.gov:

- world.topo.bathy.200407.3x21600x10800.jpg  (27.2 MB)  July, with topography and bathymetry
- gebco_08_rev_bath_21600x10800.jpg          (23.1 MB)  ocean depth, 0 to -8,000 m
- gebco_08_rev_elev_21600x10800.jpg          (14.1 MB)  land height, 0 to 6,400 m

Credit in every video description that uses them: "Imagery by NASA's Earth
Observatory (Blue Marble Next Generation, J. Allen) using ocean depths and land
heights from GEBCO".

The images and the texture cache built from them (cache/, about 500 MB) are not
committed. Fetch the images again with:

    .venv/Scripts/python.exe scripts/fetch_earth_textures.py
