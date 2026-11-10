package com.cyberhats.mixin;

import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import com.cyberfarm.client.model.DroneModel;
import com.cyberfarm.client.renderer.DroneRenderState;
import com.cyberhats.CyberHatsClient;

import net.minecraft.client.model.geom.ModelPart;

/**
 * A drone wearing a hat shows no antenna. The model is posed again from each drone's state just before it is drawn,
 * after every drone has been gathered, so its parts can only be hidden here; 26.2 has a NeoForge hook for it instead.
 */
@Mixin(DroneModel.class)
public class DroneModelMixin {
    @Shadow
    @Final
    private ModelPart antenna;

    @Inject(method = "setupAnim(Lcom/cyberfarm/client/renderer/DroneRenderState;)V", at = @At("TAIL"))
    private void cyberhats$hideAntenna(DroneRenderState state, CallbackInfo info) {
        antenna.visible = !CyberHatsClient.wearsHat(state);
    }
}
