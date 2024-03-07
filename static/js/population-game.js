// let popscore = 0;
// let popstreak = 0; // Added streak

// fetch('country-data.json')
//     .then(response => response.json())
//     .then(data => {
//         const countriesData = data;
//         loadNewChallenge(countriesData); // Pass countriesData to loadNewChallenge
//     })
//     .catch(error => {
//         console.error('Error loading country data:', error);
//         window.location.reload(); // Attempt to reload on error
//     });

// function loadNewChallenge(countriesData) {
//     // Pick two random countries
//     const indices = [];
//     while (indices.length < 2) {
//         let r = Math.floor(Math.random() * countriesData.length);
//         if (indices.indexOf(r) === -1) indices.push(r);
//     }

//     const country1 = countriesData[indices[0]];
//     const country2 = countriesData[indices[1]];

//     // Update UI with country names and images
//     updateUI(country1, country2);

//     document.getElementById('country1-img').onclick = () => submitAnswer(country1, country2, countriesData);
//     document.getElementById('country2-img').onclick = () => submitAnswer(country2, country1, countriesData);
// }

// function submitAnswer(selectedCountry, otherCountry, countriesData) {
//     if (parseInt(selectedCountry["2023 population"]) > parseInt(otherCountry["2023 population"])) {
//         alert('Correct!');
//         popscore++;
//         popstreak++;
//     } else {
//         alert('Incorrect!');
//         popstreak = 0; // Reset streak on incorrect answer
//     }

//     document.getElementById('population-score-value').textContent = popscore;
//     document.getElementById('population-streak-value').textContent = popstreak; // Update streak in UI

//     loadNewChallenge(countriesData); // Load new challenge
// }

// function updateUI(country1, country2) {
//     // Example function to update the UI with country names and images
//     const img1 = document.getElementById('country1-img');
//     img1.src = country1.image_path;
//     img1.alt = country1.country; // Add alt text for accessibility

//     const img2 = document.getElementById('country2-img');
//     img2.src = country2.image_path;
//     img2.alt = country2.country; // Add alt text for accessibility

//     // Optionally display country names to help users choose
//     document.getElementById('country1-name').textContent = country1.country;
//     document.getElementById('country2-name').textContent = country2.country;
// }
