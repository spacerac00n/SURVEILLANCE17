# Testing of Tracking feature
Note: The other cameras are props cameras, only camera 1 and 2 are usable 

In camera 2, ingest demo2.mp4 and go to the "Tracker" tab and wait for processing
Once processed finish, and threat is detected, there will be 
1) a glow on camera 2
2) notification 


# Testing of local LLM 
Turn off your wifi to simulate poor connectivity and run the app as usual 
Ensure:
1. Ollama installed and running on localhost:11434
2. Pulled the ollama model by running
```bash
ollama pull qwen3-vl:4b
``` 


The app should run fine as there is a fallback to Ollama vision model 
