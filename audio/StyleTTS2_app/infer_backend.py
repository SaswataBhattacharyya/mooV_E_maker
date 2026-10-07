from pathlib import Path
import sys
import yaml
import torch
import torchaudio
import soundfile as sf
import librosa
import numpy as np
from collections import OrderedDict
from nltk.tokenize import word_tokenize
import re

# Add StyleTTS2 to path
REPO_DIR = Path(__file__).resolve().parents[1] / "StyleTTS2"
sys.path.insert(0, str(REPO_DIR))

from models import build_model, load_ASR_models, load_F0_models, load_checkpoint
from text_utils import TextCleaner
from utils import recursive_munch, length_to_mask
from Utils.PLBERT.util import load_plbert
from Modules.diffusion.sampler import DiffusionSampler, ADPM2Sampler, KarrasSchedule

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SAMPLE_RATE = 24000

# Mel spectrogram transform
to_mel = torchaudio.transforms.MelSpectrogram(
    n_mels=80, n_fft=2048, win_length=1200, hop_length=300)
mean, std = -4, 4


class StyleTTS2Infer:
    def __init__(self, config_path, checkpoint_path):
        # Get StyleTTS2 directory for resolving relative paths
        self.styltts2_dir = Path(config_path).resolve().parent.parent
        
        # Load config
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Resolve all paths relative to StyleTTS2 directory
        ASR_config = config.get('ASR_config', False)
        ASR_path = config.get('ASR_path', False)
        if ASR_config:
            ASR_config = str(self.styltts2_dir / ASR_config)
        if ASR_path:
            ASR_path = str(self.styltts2_dir / ASR_path)
        text_aligner = load_ASR_models(ASR_path, ASR_config)
        
        F0_path = config.get('F0_path', False)
        if F0_path:
            F0_path = str(self.styltts2_dir / F0_path)
        pitch_extractor = load_F0_models(F0_path)
        
        BERT_path = config.get('PLBERT_dir', False)
        if BERT_path:
            BERT_path = str(self.styltts2_dir / BERT_path)
        plbert = load_plbert(BERT_path)
        
        # Build model
        model_params = recursive_munch(config['model_params'])
        self.model = build_model(model_params, text_aligner, pitch_extractor, plbert)
        
        # Move to device
        _ = [self.model[key].to(DEVICE) for key in self.model]
        _ = [self.model[key].eval() for key in self.model]
        
        # Load checkpoint
        params_whole = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
        params = params_whole['net']
        
        for key in self.model:
            if key in params:
                print(f'{key} loaded')
                try:
                    self.model[key].load_state_dict(params[key])
                except:
                    state_dict = params[key]
                    new_state_dict = OrderedDict()
                    for k, v in state_dict.items():
                        name = k[7:] if k.startswith('module.') else k  # remove `module.`
                        new_state_dict[name] = v
                    self.model[key].load_state_dict(new_state_dict, strict=False)
        
        _ = [self.model[key].eval() for key in self.model]
        
        # Initialize text cleaner
        self.text_cleaner = TextCleaner()
        
        # Initialize phonemizer
        try:
            import phonemizer
            self.phonemizer = phonemizer.backend.EspeakBackend(
                language='en-us', preserve_punctuation=True, with_stress=True)
        except ImportError:
            raise ImportError("phonemizer is required. Install with: pip install phonemizer")
        
        # Initialize sampler
        self.sampler = DiffusionSampler(
            self.model.diffusion.diffusion,  # First positional argument (diffusion object)
            sampler=ADPM2Sampler(),
            sigma_schedule=KarrasSchedule(sigma_min=0.0001, sigma_max=3.0, rho=9.0),
            clamp=False
        )
        
        # Store model params for inference
        self.model_params = model_params

    def _preprocess_audio(self, wave):
        """Preprocess audio for style extraction"""
        wave_tensor = torch.from_numpy(wave).float()
        mel_tensor = to_mel(wave_tensor)
        mel_tensor = (torch.log(1e-5 + mel_tensor.unsqueeze(0)) - mean) / std
        return mel_tensor

    def _compute_style(self, ref_audio_path):
        """Extract style from reference audio"""
        wave, sr = librosa.load(ref_audio_path, sr=SAMPLE_RATE)
        audio, index = librosa.effects.trim(wave, top_db=30)
        if sr != SAMPLE_RATE:
            audio = librosa.resample(audio, sr, SAMPLE_RATE)
        mel_tensor = self._preprocess_audio(audio).to(DEVICE)

        with torch.no_grad():
            ref_s = self.model.style_encoder(mel_tensor.unsqueeze(1))
            ref_p = self.model.predictor_encoder(mel_tensor.unsqueeze(1))

        return torch.cat([ref_s, ref_p], dim=1)

    def _count_tokens(self, text):
        """Count the number of tokens after tokenization"""
        try:
            ps = self.phonemizer.phonemize([text])
            ps = word_tokenize(ps[0])
            ps = ' '.join(ps)
            tokens = self.text_cleaner(ps)
            return len(tokens) + 1  # +1 for the inserted 0 at the beginning
        except:
            # Fallback: rough estimate (1 token per word + some overhead)
            return len(text.split()) * 2

    def _chunk_text_intelligently(self, text, max_tokens=450, min_tokens=100):
        """
        Intelligently chunk text into segments that are < max_tokens but not too small.
        Chunks by sentences first, then by punctuation if needed.
        """
        text = text.strip()
        if not text:
            return []
        
        # First, split by sentence endings
        sentence_endings = re.compile(r'([.!?]+)\s+')
        sentences = sentence_endings.split(text)
        
        # Recombine sentences with their punctuation
        combined_sentences = []
        for i in range(0, len(sentences) - 1, 2):
            if i + 1 < len(sentences):
                combined_sentences.append(sentences[i] + sentences[i + 1])
            else:
                combined_sentences.append(sentences[i])
        if len(sentences) % 2 == 1:
            combined_sentences.append(sentences[-1])
        
        # Filter out empty sentences
        combined_sentences = [s.strip() for s in combined_sentences if s.strip()]
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for sentence in combined_sentences:
            sentence_tokens = self._count_tokens(sentence)
            
            # If a single sentence is too long, split it further
            if sentence_tokens > max_tokens:
                # First, save current chunk if it exists
                if current_chunk:
                    chunks.append(' '.join(current_chunk))
                    current_chunk = []
                    current_tokens = 0
                
                # Split long sentence by commas, semicolons, or other punctuation
                sub_sentences = re.split(r'([,;:]\s+)', sentence)
                sub_sentences = [s for s in sub_sentences if s.strip()]
                
                for sub_sent in sub_sentences:
                    sub_tokens = self._count_tokens(sub_sent)
                    
                    if current_tokens + sub_tokens > max_tokens and current_chunk:
                        # Save current chunk
                        chunks.append(' '.join(current_chunk))
                        current_chunk = [sub_sent]
                        current_tokens = sub_tokens
                    else:
                        current_chunk.append(sub_sent)
                        current_tokens += sub_tokens
            else:
                # Check if adding this sentence would exceed max_tokens
                if current_tokens + sentence_tokens > max_tokens and current_chunk:
                    # Save current chunk and start new one
                    chunks.append(' '.join(current_chunk))
                    current_chunk = [sentence]
                    current_tokens = sentence_tokens
                else:
                    # Add to current chunk
                    current_chunk.append(sentence)
                    current_tokens += sentence_tokens
        
        # Add remaining chunk
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        # Filter out chunks that are too small (unless they're the only chunk)
        if len(chunks) > 1:
            chunks = [chunk for chunk in chunks if self._count_tokens(chunk) >= min_tokens or len(chunks) == 1]
        
        return chunks if chunks else [text]

    @torch.no_grad()
    def _synthesize_chunk(self, text_chunk, ref_s, alpha=0.3, beta=0.7, 
                          diffusion_steps=5, embedding_scale=1):
        """Synthesize a single chunk of text"""
        text_chunk = text_chunk.strip()
        if not text_chunk:
            return None
        
        # Phonemize text
        ps = self.phonemizer.phonemize([text_chunk])
        ps = word_tokenize(ps[0])
        ps = ' '.join(ps)
        tokens = self.text_cleaner(ps)
        tokens.insert(0, 0)
        tokens = torch.LongTensor(tokens).to(DEVICE).unsqueeze(0)

        input_lengths = torch.LongTensor([tokens.shape[-1]]).to(DEVICE)
        text_mask = length_to_mask(input_lengths).to(DEVICE)

        t_en = self.model.text_encoder(tokens, input_lengths, text_mask)
        bert_dur = self.model.bert(tokens, attention_mask=(~text_mask).int())
        d_en = self.model.bert_encoder(bert_dur).transpose(-1, -2)

        s_pred = self.sampler(
            noise=torch.randn((1, 256)).unsqueeze(1).to(DEVICE),
            embedding=bert_dur,
            embedding_scale=embedding_scale,
            features=ref_s,
            num_steps=diffusion_steps
        ).squeeze(1)

        s = s_pred[:, 128:]
        ref = s_pred[:, :128]

        ref = alpha * ref + (1 - alpha) * ref_s[:, :128]
        s = beta * s + (1 - beta) * ref_s[:, 128:]

        d = self.model.predictor.text_encoder(d_en, s, input_lengths, text_mask)

        x, _ = self.model.predictor.lstm(d)
        duration = self.model.predictor.duration_proj(x)

        duration = torch.sigmoid(duration).sum(axis=-1)
        pred_dur = torch.round(duration.squeeze()).clamp(min=1)

        pred_aln_trg = torch.zeros(input_lengths, int(pred_dur.sum().data))
        c_frame = 0
        for i in range(pred_aln_trg.size(0)):
            pred_aln_trg[i, c_frame:c_frame + int(pred_dur[i].data)] = 1
            c_frame += int(pred_dur[i].data)

        # Encode prosody
        en = (d.transpose(-1, -2) @ pred_aln_trg.unsqueeze(0).to(DEVICE))
        if self.model_params.decoder.type == "hifigan":
            asr_new = torch.zeros_like(en)
            asr_new[:, :, 0] = en[:, :, 0]
            asr_new[:, :, 1:] = en[:, :, 0:-1]
            en = asr_new

        F0_pred, N_pred = self.model.predictor.F0Ntrain(en, s)

        asr = (t_en @ pred_aln_trg.unsqueeze(0).to(DEVICE))
        if self.model_params.decoder.type == "hifigan":
            asr_new = torch.zeros_like(asr)
            asr_new[:, :, 0] = asr[:, :, 0]
            asr_new[:, :, 1:] = asr[:, :, 0:-1]
            asr = asr_new

        out = self.model.decoder(asr, F0_pred, N_pred, ref.squeeze().unsqueeze(0))

        # Return audio (remove weird pulse at end)
        wav = out.squeeze().cpu().numpy()[..., :-50]
        return wav

    @torch.no_grad()
    def synthesize(self, text, ref_audio_path, out_path, alpha=0.3, beta=0.7, 
                   diffusion_steps=5, embedding_scale=1):
        """Synthesize speech from text using reference audio style with intelligent chunking"""
        # Clear CUDA cache before inference to free up memory
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        text = text.strip()
        if not text:
            raise ValueError("Text cannot be empty")
        
        # Compute reference style once (reused for all chunks)
        ref_s = self._compute_style(ref_audio_path)
        
        # Chunk the text intelligently
        chunks = self._chunk_text_intelligently(text, max_tokens=450, min_tokens=100)
        
        # Process each chunk and collect audio outputs
        audio_chunks = []
        for i, chunk in enumerate(chunks):
            if chunk.strip():
                wav_chunk = self._synthesize_chunk(
                    chunk, ref_s, alpha, beta, diffusion_steps, embedding_scale
                )
                if wav_chunk is not None:
                    audio_chunks.append(wav_chunk)
                
                # Clear cache between chunks to free memory
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
        
        # Concatenate all audio chunks
        if audio_chunks:
            final_audio = np.concatenate(audio_chunks)
            sf.write(out_path, final_audio, SAMPLE_RATE)
        else:
            raise ValueError("No audio was generated from the input text")
        
        # Clear CUDA cache after inference to free up memory
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
