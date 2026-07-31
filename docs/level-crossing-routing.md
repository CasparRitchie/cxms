# Level-crossing journey routing

The journey chooser is available without third-party credentials. In that
state it shows the saved destination, parking walk and current crossing
prediction, but deliberately does not invent a road or A27 journey time.

## Enable live journey times on Heroku

Create a Mapbox access token and a what3words API key, then configure both on
the existing CXMS Heroku app:

```sh
heroku config:set MAPBOX_ACCESS_TOKEN='your-mapbox-token' --app YOUR_CXMS_APP
heroku config:set WHAT3WORDS_API_KEY='your-what3words-key' --app YOUR_CXMS_APP
```

The keys remain server-side. The browser only receives journey durations,
distances, route classifications and destination display details.

The default start is the public centroid of Willowbed Drive, rather than a
house or a device location. It can be moved later without a code change:

```sh
heroku config:set LEVEL_CROSSING_ORIGIN_COORDINATES='longitude,latitude' --app YOUR_CXMS_APP
```

## How a recommendation is calculated

1. what3words converts the saved parking/destination points and the three
   crossing locations to coordinates.
2. Mapbox `driving-traffic` returns the fastest route and up to two meaningful
   alternatives using current and historic traffic.
3. Full route geometry identifies which tracked crossings each route passes.
   Road-step references identify an A27 alternative when one is returned.
4. The browser adds the current predicted barrier wait and the saved
   parking-to-door walk to each driving time.
5. A Mapbox walking route is shown alongside the driving choices.

Journey results are cached for 75 seconds in each web process. what3words
coordinates are retained in memory for the life of the process. Waze remains
the hand-off for turn-by-turn navigation.

Provider references:

- [Mapbox Directions API](https://docs.mapbox.com/api/navigation/directions/)
- [what3words convert-to-coordinates API](https://developer.what3words.com/public-api/docs)
