// let score = 0;
// let streak = 0;
// let currentCountry = ""; // Variable to keep track of the current country's name

// function loadNewCountry() {
//   fetch('/games/country-data')
//     .then(response => response.json())
//     .then(data => {
//       // Extract the correct country information
//       const country = data.correct_country;
//       currentCountry = country.name; // Update the current country name

//       // Update the country outline image
//       const countryImg = document.getElementById('country-outline');
//       countryImg.src = country.outline;
//       countryImg.alt = country.name; // Helpful for accessibility, though not used for validation

//       // Clear previous options
//       const optionsContainer = document.getElementById('options-container');
//       optionsContainer.innerHTML = '';

//       // Create buttons for each option
//       data.options.forEach(option => {
//         const button = document.createElement('button');
//         button.textContent = option;
//         button.onclick = function() { submitAnswer(option); };
//         optionsContainer.appendChild(button);
//       });
//     })
//     .catch(error => console.error('Error fetching country data:', error));
// }

// function submitAnswer(selectedCountry) {
//   if (selectedCountry === currentCountry) {
//     alert('Correct!');
//     score++;
//     streak++;
//   } else {
//     alert(`Incorrect, the correct country was ${currentCountry}.`);
//     streak = 0;
//   }
//   // Update score and streak display
//   document.getElementById('score-value').textContent = score;
//   document.getElementById('streak-value').textContent = streak;

//   loadNewCountry(); // Load a new country for the next round
// }

// document.addEventListener('DOMContentLoaded', loadNewCountry);
