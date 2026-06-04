export type EdgeRefineOptions = {
  contract: number;
  feather: number;
  defringe: number;
  threshold: number;
};

export function refineImageDataEdges(imageData: ImageData, options: EdgeRefineOptions) {
  const contract = Math.max(0, Number(options.contract) || 0);
  const feather = Math.max(0, Number(options.feather) || 0);
  const defringe = Math.max(0, Math.round(options.defringe));
  const threshold = clampByte(options.threshold);

  if (contract > 0 || feather > 0) {
    contractImageDataAlpha(imageData, contract, feather, threshold);
  }
  if (defringe > 0) {
    decontaminateEdgeColors(imageData, defringe, threshold);
  }
}

function contractImageDataAlpha(imageData: ImageData, amount: number, feather: number, threshold: number) {
  const alpha = readAlpha(imageData);
  const mask = readAlphaMask(alpha, threshold);
  const distance = readEdgeDistance(mask, imageData.width, imageData.height);

  // 浏览器端实时预览采用近似距离场，和后端 OpenCV 距离场保持相同意图。
  // 它比逐圈腐蚀更适合斜线和弧线，去边色后不会把台阶边缘强调得那么明显。
  for (let index = 0; index < alpha.length; index += 1) {
    const alphaIndex = index * 4 + 3;
    const edgeDistance = distance[index];
    const weight = feather <= 0 ? (edgeDistance > amount ? 1 : 0) : smoothStep((edgeDistance - amount) / feather);
    imageData.data[alphaIndex] = Math.round(alpha[index] * weight);
  }
}

function decontaminateEdgeColors(imageData: ImageData, radius: number, threshold: number) {
  const alpha = readAlpha(imageData);
  const mask = readAlphaMask(alpha, threshold);
  const distance = readEdgeDistance(mask, imageData.width, imageData.height);
  const target = new Uint8Array(alpha.length);
  const filled = new Uint8Array(alpha.length);
  let hasTarget = false;
  let hasFilled = false;

  for (let index = 0; index < alpha.length; index += 1) {
    const edgeDistance = distance[index];
    if (alpha[index] > 0 && edgeDistance > 0 && edgeDistance <= radius + 1) {
      target[index] = 1;
      hasTarget = true;
    }
    if (alpha[index] >= Math.max(96, threshold) && edgeDistance > radius + 1) {
      filled[index] = 1;
      hasFilled = true;
    }
  }
  if (!hasTarget || !hasFilled) return;

  for (let iteration = 0; iteration < radius + 2; iteration += 1) {
    const updates: Array<[number, number, number, number]> = [];
    for (let y = 0; y < imageData.height; y += 1) {
      for (let x = 0; x < imageData.width; x += 1) {
        const index = y * imageData.width + x;
        if (!target[index] || filled[index]) continue;

        let red = 0;
        let green = 0;
        let blue = 0;
        let count = 0;
        for (let dy = -1; dy <= 1; dy += 1) {
          for (let dx = -1; dx <= 1; dx += 1) {
            const sampleX = x + dx;
            const sampleY = y + dy;
            if (sampleX < 0 || sampleY < 0 || sampleX >= imageData.width || sampleY >= imageData.height) continue;
            const sampleIndex = sampleY * imageData.width + sampleX;
            if (!filled[sampleIndex]) continue;
            const dataIndex = sampleIndex * 4;
            red += imageData.data[dataIndex];
            green += imageData.data[dataIndex + 1];
            blue += imageData.data[dataIndex + 2];
            count += 1;
          }
        }
        if (count > 0) {
          updates.push([index, red / count, green / count, blue / count]);
        }
      }
    }
    if (!updates.length) break;
    for (const [index, red, green, blue] of updates) {
      const dataIndex = index * 4;
      imageData.data[dataIndex] = Math.round(red);
      imageData.data[dataIndex + 1] = Math.round(green);
      imageData.data[dataIndex + 2] = Math.round(blue);
      filled[index] = 1;
    }
  }
}

function readAlpha(imageData: ImageData) {
  const alpha = new Uint8ClampedArray(imageData.width * imageData.height);
  for (let index = 0; index < alpha.length; index += 1) {
    alpha[index] = imageData.data[index * 4 + 3];
  }
  return alpha;
}

function readAlphaMask(alpha: Uint8ClampedArray, threshold: number) {
  const mask = new Uint8Array(alpha.length);
  for (let index = 0; index < mask.length; index += 1) {
    mask[index] = alpha[index] >= threshold ? 1 : 0;
  }
  return mask;
}

function readEdgeDistance(mask: Uint8Array, width: number, height: number) {
  const distance = new Float32Array(mask.length);
  const maxDistance = width + height;
  for (let index = 0; index < mask.length; index += 1) {
    distance[index] = mask[index] ? maxDistance : 0;
  }

  const diagonal = Math.SQRT2;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = y * width + x;
      if (!mask[index]) continue;
      let value = distance[index];
      if (x > 0) value = Math.min(value, distance[index - 1] + 1);
      if (y > 0) value = Math.min(value, distance[index - width] + 1);
      if (x > 0 && y > 0) value = Math.min(value, distance[index - width - 1] + diagonal);
      if (x + 1 < width && y > 0) value = Math.min(value, distance[index - width + 1] + diagonal);
      distance[index] = value;
    }
  }
  for (let y = height - 1; y >= 0; y -= 1) {
    for (let x = width - 1; x >= 0; x -= 1) {
      const index = y * width + x;
      if (!mask[index]) continue;
      let value = distance[index];
      if (x + 1 < width) value = Math.min(value, distance[index + 1] + 1);
      if (y + 1 < height) value = Math.min(value, distance[index + width] + 1);
      if (x + 1 < width && y + 1 < height) value = Math.min(value, distance[index + width + 1] + diagonal);
      if (x > 0 && y + 1 < height) value = Math.min(value, distance[index + width - 1] + diagonal);
      distance[index] = value;
    }
  }
  return distance;
}

function smoothStep(value: number) {
  const t = Math.min(1, Math.max(0, value));
  return t * t * (3 - 2 * t);
}

function clampByte(value: number) {
  return Math.min(255, Math.max(0, Math.round(value)));
}
