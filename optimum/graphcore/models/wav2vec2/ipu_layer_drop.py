# coding=utf-8
# Copyright 2021 The Fairseq Authors and the HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
These are the same blocks as in the original implementation in transformers,
but with a traceable implementation of LayerDrop.
"""

import torch
from torch.nn import functional as F

from transformers.modeling_outputs import BaseModelOutput
from transformers.models.wav2vec2.modeling_wav2vec2 import (
    Wav2Vec2Adapter,
    Wav2Vec2Encoder,
    Wav2Vec2EncoderStableLayerNorm,
)


class IPUWav2Vec2Encoder(Wav2Vec2Encoder):
    def forward(
        self,
        hidden_states,
        attention_mask=None,
        output_attentions=False,
        output_hidden_states=False,
        return_dict=True,
    ):
        all_self_attentions = None
        all_hidden_states = None

        if output_attentions:
            raise ValueError("output_attetntions=True is not supported " "for IPUWav2Vec2Encoder")
        if output_hidden_states:
            raise ValueError("output_hidden_states=True is not supported " "for IPUWav2Vec2Encoder")

        pad_length = 0
        if attention_mask is not None:
            # make sure padded tokens output 0
            hidden_states[~attention_mask] = 0.0

            sequence_length_padding_divisor = 4
            # Pad attention mask to more divisible length
            remainder = attention_mask.size(-1) % sequence_length_padding_divisor

            if remainder != 0:
                pad_length = sequence_length_padding_divisor - remainder
                attention_mask = F.pad(
                    attention_mask,
                    # Want e.g. (..., 999) -> (..., 1000)
                    pad=(0, pad_length),
                    value=0.0,
                )

            # extend attention_mask
            attention_mask = (1.0 - attention_mask[:, None, None, :].to(dtype=hidden_states.dtype)) * -10000.0
            attention_mask = attention_mask.expand(
                attention_mask.shape[0], 1, attention_mask.shape[-1], attention_mask.shape[-1]
            )

        position_embeddings = self.pos_conv_embed(hidden_states)
        hidden_states = hidden_states + position_embeddings
        hidden_states = self.layer_norm(hidden_states)
        hidden_states = self.dropout(hidden_states)

        hidden_states = F.pad(
            hidden_states,
            # Want e.g. (..., 999, 768) -> (..., 1000, 768)
            pad=(0, 0, 0, pad_length),
        )

        for layer in self.layers:
            # add LayerDrop (see https://arxiv.org/abs/1909.11556 for description)
            dropout_probability = torch.rand(tuple())
            skip_the_layer = self.training and (dropout_probability < self.config.layerdrop)
            layer_outputs = layer(hidden_states, attention_mask=attention_mask, output_attentions=output_attentions)
            hidden_states = torch.where(torch.BoolTensor([skip_the_layer]), hidden_states, layer_outputs[0])

        # Remove padded values
        # Want e.g. (..., 1000, 768) -> (..., 999, 768)
        if pad_length > 0:
            hidden_states = hidden_states[..., 0:(-pad_length), :]

        if not return_dict:
            return tuple(v for v in [hidden_states, all_hidden_states, all_self_attentions] if v is not None)

        return BaseModelOutput(
            last_hidden_state=hidden_states,
            hidden_states=all_hidden_states,
            attentions=all_self_attentions,
        )


class IPUWav2Vec2EncoderStableLayerNorm(Wav2Vec2EncoderStableLayerNorm):
    def forward(
        self,
        hidden_states,
        attention_mask=None,
        output_attentions=False,
        output_hidden_states=False,
        return_dict=True,
    ):
        all_self_attentions = None
        all_hidden_states = None

        if output_attentions:
            raise ValueError("output_attetntions=True is not supported " "for IPUWav2Vec2EncoderStableLayerNorm")
        if output_hidden_states:
            raise ValueError("output_hidden_states=True is not supported " "for IPUWav2Vec2EncoderStableLayerNorm")

        pad_length = 0
        if attention_mask is not None:
            # make sure padded tokens output 0
            hidden_states[~attention_mask] = 0.0

            sequence_length_padding_divisor = 4
            # Pad attention mask to more divisible length
            remainder = attention_mask.size(-1) % sequence_length_padding_divisor

            if remainder != 0:
                pad_length = sequence_length_padding_divisor - remainder
                attention_mask = F.pad(
                    attention_mask,
                    # Want e.g. (..., 999) -> (..., 1000)
                    pad=(0, pad_length),
                    value=0.0,
                )

            # extend attention_mask
            attention_mask = (1.0 - attention_mask[:, None, None, :].to(dtype=hidden_states.dtype)) * -10000.0
            attention_mask = attention_mask.expand(
                attention_mask.shape[0], 1, attention_mask.shape[-1], attention_mask.shape[-1]
            )

        position_embeddings = self.pos_conv_embed(hidden_states)
        hidden_states = hidden_states + position_embeddings
        hidden_states = self.dropout(hidden_states)

        hidden_states = F.pad(
            hidden_states,
            # Want e.g. (..., 999, 768) -> (..., 1000, 768)
            pad=(0, 0, 0, pad_length),
        )

        for layer in self.layers:
            # add LayerDrop (see https://arxiv.org/abs/1909.11556 for description)
            dropout_probability = torch.rand(tuple())
            skip_the_layer = self.training and (dropout_probability < self.config.layerdrop)
            layer_outputs = layer(hidden_states, attention_mask=attention_mask, output_attentions=output_attentions)
            hidden_states = torch.where(torch.BoolTensor([skip_the_layer]), hidden_states, layer_outputs[0])

        # Remove padded values
        # Want e.g. (..., 1000, 768) -> (..., 999, 768)
        if pad_length > 0:
            hidden_states = hidden_states[..., 0:(-pad_length), :]

        hidden_states = self.layer_norm(hidden_states)

        if not return_dict:
            return tuple(v for v in [hidden_states, all_hidden_states, all_self_attentions] if v is not None)

        return BaseModelOutput(
            last_hidden_state=hidden_states,
            hidden_states=all_hidden_states,
            attentions=all_self_attentions,
        )


class IPUWav2Vec2Adapter(Wav2Vec2Adapter):
    def forward(self, hidden_states):
        # down project hidden_states if necessary
        if self.proj is not None and self.proj_layer_norm is not None:
            hidden_states = self.proj(hidden_states)
            hidden_states = self.proj_layer_norm(hidden_states)

        hidden_states = hidden_states.transpose(1, 2)

        for layer in self.layers:
            layerdrop_prob = torch.rand(tuple())
            layer_output = layer(hidden_states)
            use_the_layer = not self.training or (layerdrop_prob > self.layerdrop)
            hidden_states = torch.where(torch.BoolTensor([use_the_layer]), layer_output, hidden_states)

        hidden_states = hidden_states.transpose(1, 2)
        return hidden_states
