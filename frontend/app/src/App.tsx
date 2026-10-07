import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./pages/Home";
import StoryBuilder from "./pages/StoryBuilder";
import MediaComposer from "./pages/MediaComposer";
import AutomationStudio from "./pages/AutomationStudio";
import AgentStatus from "./pages/AgentStatus";
import AudioStudio from "./pages/AudioStudio";
import MusicSound from "./pages/MusicSound";
import AudioUtilities from "./pages/AudioUtilities";
import NotFound from "./pages/NotFound";
import VideoRepertoire from "./pages/VideoRepertoire";
import StoryCanvas from "./pages/StoryCanvas";
import AudioReconstruct from "./pages/AudioReconstruct";
import Generate from "./pages/Generate";
import ImageDetailer from "./pages/ImageDetailer";
import ManualDirector from "./pages/ManualDirector";
import ProductionWorkspace from "./pages/ProductionWorkspace";
import StyleLibrary from "./pages/StyleLibrary";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/story" element={<StoryBuilder />} />
          <Route path="/canvas" element={<StoryCanvas />} />
          <Route path="/media" element={<MediaComposer />} />
          <Route path="/generate" element={<Generate />} />
          <Route path="/image-detailer" element={<ImageDetailer />} />
          <Route path="/audio" element={<AudioStudio />} />
          <Route path="/audio-reconstruct" element={<AudioReconstruct />} />
          <Route path="/music-sound" element={<MusicSound />} />
          <Route path="/audio-tools" element={<AudioUtilities />} />
          <Route path="/automation" element={<AutomationStudio />} />
          <Route path="/status" element={<AgentStatus />} />
          <Route path="/video-repertoire" element={<VideoRepertoire />} />
          <Route path="/video-summariser" element={<VideoRepertoire />} />
          <Route path="/manual-director" element={<ManualDirector />} />
          <Route path="/production" element={<ProductionWorkspace />} />
          <Route path="/style-library" element={<StyleLibrary />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
