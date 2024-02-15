// Example country data
const countries = [
  { name: "France", outline: "/static/images/games-images/country-outlines/France.png" },
  { name: "Germany", outline: "/static/images/games-images/country-outlines/Germany.png" },
  // Add more countries
];

let score = 0;
let streak = 0;

let currentCountry = ""; // Variable to keep track of the current country's name

function loadNewCountry() {
  const randomIndex = Math.floor(Math.random() * countries.length);
  const country = countries[randomIndex];
  currentCountry = country.name; // Update the current country name

  // Update the country outline image and its alt attribute
  const countryImg = document.getElementById('country-outline');
  countryImg.src = country.outline;
  countryImg.alt = country.name; // Update alt to reflect the current country

  // Clear previous options
  const optionsContainer = document.getElementById('options-container');
  optionsContainer.innerHTML = '';

  // Shuffle countries array and pick the first 4 for options
  const shuffledCountries = countries.sort(() => 0.5 - Math.random()).slice(0, 4);

  // Ensure the correct answer is among the options
  if (!shuffledCountries.find(opt => opt.name === country.name)) {
      shuffledCountries.pop(); // Remove one option
      shuffledCountries.push(country); // Add the correct answer
  }

  // Shuffle again to randomize the position of the correct answer
  const options = shuffledCountries.sort(() => 0.5 - Math.random());

  // Create buttons for each option
  options.forEach(option => {
      const button = document.createElement('button');
      button.textContent = option.name;
      button.onclick = function() { submitAnswer(option.name); };
      optionsContainer.appendChild(button);
  });
}


function submitAnswer(selectedCountry) {
    // Use the currentCountry variable to check the answer instead of the alt attribute
    if (selectedCountry === currentCountry) {
        alert('Correct!');
        score++;
        streak++;
    } else {
        alert(`Incorrect, the correct country was ${currentCountry}.`);
        streak = 0;
    }
    // Update score and streak display and load a new country
    document.getElementById('score-value').textContent = score;
    document.getElementById('streak-value').textContent = streak;

    loadNewCountry();
}

// Make sure to call loadNewCountry when the page loads to start the game
document.addEventListener('DOMContentLoaded', loadNewCountry);

// Initially load a country when the page is ready
document.addEventListener('DOMContentLoaded', loadNewCountry);
