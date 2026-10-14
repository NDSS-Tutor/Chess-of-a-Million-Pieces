WEATHER_CONDITIONS_BY_STAGE = {
    'sky': ('Sunny', 'Cloudy', 'Rainy', 'Windy', 'Snowy', 'Foggy', 'Stormy'),
    'plains': ('Sunny', 'Cloudy', 'Rainy', 'Windy', 'Drought', 'Thunderstorm', 'Foggy'),
    'tunnels': ('Dripping', 'Damp Mist', 'Cold Draft', 'Underground Rain', 'Still Air', 'Foggy'),
    'caves': ('Dustfall', 'Cold', 'Stone Hail', 'Crystal Haze', 'Dripping', 'Cave Fog'),
}

WEATHER_EFFECTS_BY_STAGE = {
    'sky': {
        'Stormy': {
            'type': 'storm_clouds',
            'clump_count': 4,
            'clump_min_tiles': 3,
            'clump_max_tiles': 6,
            'turns_before_shock': 1,
            'shock_duration_turns': 4,
        },
    },
    'caves': {
        'Cave Fog': {
            'type': 'fog_of_war',
            'visibility_distance': 1,
        },
        'Crystal Haze': {
            'type': 'piece_hallucinations',
            'duplicate_min': 2,
            'duplicate_max': 3,
            'hallucinations_disappear_when_attacked': True,
            'hallucinations_disappear_when_attacking': True,
            'randomize_real_piece_location': True,
        },
    },
}
