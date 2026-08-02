# Level-crossing journey routing

The journey chooser is available without third-party credentials. In that
state it shows the saved destination, parking walk and current crossing
prediction, but deliberately does not invent a road or A27 journey time.

## Enable live journey times on Heroku

Create a Mapbox public access token, then configure it on the existing CXMS
Heroku app:

```sh
heroku config:set MAPBOX_ACCESS_TOKEN='your-mapbox-token' --app YOUR_CXMS_APP
```

The token remains server-side. The browser only receives journey durations,
distances, route classifications and destination display details.

The default start is the public centroid of Willowbed Drive, rather than a
house or a device location. It can be moved later without a code change:

```sh
heroku config:set LEVEL_CROSSING_ORIGIN_COORDINATES='longitude,latitude' --app YOUR_CXMS_APP
```

## How a recommendation is calculated

1. Mapbox Search temporarily resolves the saved named destination near
   Chichester. The what3words addresses remain visible references and do not
   require a paid API plan.
2. CXMS asks Mapbox `driving-traffic` to time explicit local route families:
   Whyke Road, the A27, north via Quarry Lane and Orchard Street, or Quarry
   Lane for destinations north and east of the city. This avoids relying on
   Mapbox's generic alternatives to discover locally useful choices.
3. Active local road closures are excluded from every driving request. Basin
   Road is closed by default and is also shown as closed in the crossing
   selector. Once it reopens, disable that override with:

   ```sh
   heroku config:set LEVEL_CROSSING_ROAD_CLOSURES='none' --app YOUR_CXMS_APP
   ```

   More road IDs can be supported by extending `ROAD_CLOSURES` in
   `services/level_crossing/routing.py`.
4. The browser adds the current predicted barrier wait and the saved
   parking-to-door walk to each driving time.
5. A Mapbox walking route is shown alongside the driving choices.

Journey results are cached for 75 seconds in each web process. Mapbox search
results are cached for ten minutes. Waze remains the hand-off for turn-by-turn
navigation.

Provider references:

- [Mapbox Directions API](https://docs.mapbox.com/api/navigation/directions/)
- [Mapbox Search Box API](https://docs.mapbox.com/api/search/search-box/)
